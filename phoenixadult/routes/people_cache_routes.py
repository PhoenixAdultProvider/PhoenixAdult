from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, get_args
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from phoenixadult.config import image_base_url
from phoenixadult.config.env import env
from phoenixadult.routes import nav_username, read_json_body, render_page
from phoenixadult.utils import db
from phoenixadult.utils.auth.user_auth import admin_auth_guard, csrf_guard, user_auth_guard
from phoenixadult.utils.cache import scene_store
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.images import face_crop, face_crop_log
from phoenixadult.utils.images.proxy import LOCAL_IMAGES
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.people.cache import cache_photo, index_conn, purge, restore_original, set_gender
from phoenixadult.utils.people.image_source import KNOWN_SOURCES
from phoenixadult.utils.people.sources import ALL_SOURCES
from phoenixadult.utils.people.sources.local_storage import local_storage_source
from phoenixadult.utils.people.types import Gender, PersonLookupContext, PersonSource, PersonType, parse_person_filename
from phoenixadult.utils.processors.title_case import title_case

router = APIRouter(dependencies=[Depends(user_auth_guard), Depends(csrf_guard)])
_admin = [Depends(admin_auth_guard)]

FETCHABLE_SOURCES = [source for source in ALL_SOURCES if source.name != local_storage_source.name]
_BULK_CONCURRENCY = 3
_BULK_MAX = 250

_GENDERS = [('', 'gn', 'None'), ('male', 'gm', 'Male'), ('female', 'gf', 'Female'), ('trans', 'gt', 'Trans')]
_ROLE_CSS = {'actor': 'r-actor', 'director': 'r-director', 'producer': 'r-producer'}
_TABS = [
    ('actors-female', 'Female Actors'),
    ('actors-male', 'Male Actors'),
    ('actors-trans', 'Trans Actors'),
    ('actors-unknown', 'Unknown Actors'),
    ('directors', 'Directors'),
    ('producers', 'Producers'),
]


@lru_cache(maxsize=8192)
def _display_name(text: str) -> str:
    return title_case(text, type='name')


def _parse_filename(filename: str) -> tuple[str, str, str] | None:
    role, slug, gender = parse_person_filename(filename)
    if role not in get_args(PersonType) or not slug:
        return None
    return role, _display_name(slug.replace('-', ' ')), gender


def _entry(relpath: str, mtime: float, log: dict[str, Any]) -> dict[str, Any] | None:
    subpath, _, filename = relpath.rpartition('/')
    parsed = _parse_filename(filename)
    if not parsed:
        return None
    role, name, gender = parsed
    log_name = str(log.get('name') or '').strip()
    return {
        'name': _display_name(log_name) if log_name else name,
        'filename': filename,
        'relpath': relpath,
        'type': subpath.replace('/', '-'),
        'role': role,
        'gender': gender,
        'upstream_url': log.get('upstream_url', ''),
        'source': log.get('source', ''),
        'cropped': bool(log.get('cropped')),
        'ts': log.get('ts') or datetime.fromtimestamp(mtime, UTC).strftime('%Y-%m-%d %H:%M:%S'),
        'mtime': mtime,
    }


def _list_people() -> list[dict[str, Any]]:
    rows = index_conn().execute('SELECT rel_path, mtime FROM people_images ORDER BY rel_path').fetchall()
    logs = face_crop_log.entries_by_path()
    out = [_entry(str(r['rel_path']), float(r['mtime']), logs.get(str(r['rel_path']), {})) for r in rows]
    kept = [e for e in out if e is not None]
    kept.sort(key=lambda e: e['mtime'], reverse=True)
    return kept


def _gender_of(gender: str) -> Gender:
    match gender:
        case 'male' | 'female' | 'trans':
            return gender
        case _:
            return ''


def _display_entry(entry: dict[str, Any]) -> dict[str, Any]:
    name = str(entry.get('name', ''))
    filename = str(entry.get('filename', ''))
    relpath = str(entry.get('relpath', filename))
    gender_norm = _gender_of(str(entry.get('gender', '')))
    return {
        **entry,
        'gender_norm': gender_norm,
        'gcss': next(css for key, css, _ in _GENDERS if key == gender_norm),
        'role_css': _ROLE_CSS.get(str(entry.get('role', '')), ''),
        'local_src': f'{LOCAL_IMAGES}{quote(relpath, safe="/")}?v={int(entry.get("mtime", 0))}',
        'upstream_quoted': quote(str(entry.get('upstream_url', '')), safe=''),
        'search_key': name.casefold(),
        'single': len(name.split()) == 1,
    }


PAGE_SIZE = 200
_BLANK_SOURCE = '__blank__'

_TAB_SQL = "replace(rtrim(rtrim(p.rel_path, replace(p.rel_path, '/', '')), '/'), '/', '-')"
_NAME_SQL = "coalesce(nullif(trim(json_extract(c.entry, '$.name')), ''), replace(p.slug, '-', ' '))"
_SOURCE_SQL = "coalesce(c.source, '')"
_FROM_SQL = 'FROM people_images p LEFT JOIN crop_log c ON c.rel_path = p.rel_path'

_FLAGS = {
    'cropped': "coalesce(json_extract(c.entry, '$.cropped'), 0)",
    'noupstream': "coalesce(json_extract(c.entry, '$.upstream_url'), '') = ''",
    'generic': f"{_SOURCE_SQL} = 'Generic'",
    'single': f"instr(trim({_NAME_SQL}), ' ') = 0",
}


@dataclass
class PeopleFilters:
    type: str = ''
    q: str = ''
    source: str = ''
    cropped: bool = False
    noupstream: bool = False
    generic: bool = False
    single: bool = False
    offset: Annotated[int, Query(ge=0)] = 0
    limit: Annotated[int, Query(ge=1, le=500)] = PAGE_SIZE

    @property
    def needle(self) -> str:
        return self.q.strip().casefold()

    @property
    def wanted_source(self) -> str:
        return '' if self.source == _BLANK_SOURCE else self.source

    def flags(self) -> list[str]:
        return [sql for name, sql in _FLAGS.items() if getattr(self, name)]


def _pick_tab(filters: PeopleFilters, counts: dict[str, int], pick_default: bool) -> str:
    if pick_default:
        return next((t for t, _ in _TABS if counts[t]), _TABS[0][0])
    return filters.type if any(t == filters.type for t, _ in _TABS) else ''


def _where(filters: PeopleFilters, tab: str) -> tuple[str, list[Any]]:
    terms: list[tuple[str, tuple[Any, ...]]] = [(sql, ()) for sql in filters.flags()]
    if tab:
        terms.append((f'{_TAB_SQL} = ?', (tab,)))
    if filters.source:
        terms.append((f'{_SOURCE_SQL} = ?', (filters.wanted_source,)))
    if filters.needle:
        terms.append((f"casefold({_NAME_SQL}) LIKE ? ESCAPE '\\'", (db.like_contains(filters.needle),)))
    where = ' AND '.join(sql for sql, _ in terms)
    return (f'WHERE {where}' if where else ''), [arg for _, args in terms for arg in args]


def _listing(filters: PeopleFilters, pick_default: bool = False) -> dict[str, Any]:
    conn = index_conn()
    conn.create_function('casefold', 1, lambda s: s.casefold() if isinstance(s, str) else s, deterministic=True)
    counts = dict.fromkeys((t for t, _ in _TABS), 0)
    library = 0
    for row in conn.execute(f'SELECT {_TAB_SQL} AS tab, count(*) AS n FROM people_images p GROUP BY tab'):
        library += int(row['n'])
        if row['tab'] in counts:
            counts[row['tab']] = int(row['n'])
    tab = _pick_tab(filters, counts, pick_default)
    where, args = _where(filters, tab)
    total = int(conn.execute(f'SELECT count(*) {_FROM_SQL} {where}', args).fetchone()[0])
    page = conn.execute(
        f'SELECT p.rel_path, p.mtime, c.entry, c.source {_FROM_SQL} {where} ORDER BY p.mtime DESC, p.rel_path LIMIT ? OFFSET ?',
        [*args, filters.limit, filters.offset],
    ).fetchall()
    entries = []
    for row in page:
        log = face_crop_log.parse_entry(str(row['entry']), str(row['source'] or '')) if row['entry'] is not None else None
        entry = _entry(str(row['rel_path']), float(row['mtime']), log or {})
        if entry is not None:
            entries.append(_display_entry(entry))
    tab_where, tab_args = _where(PeopleFilters(), tab)
    present = [str(r[0]) for r in conn.execute(f'SELECT DISTINCT {_SOURCE_SQL} {_FROM_SQL} {tab_where}', tab_args)]
    return {
        'entries': entries,
        'total': total,
        'counts': counts,
        'tab': tab,
        'sources': sorted((s for s in present if s), key=str.casefold),
        'has_unrecorded': '' in present,
        'library': library,
        'pageSize': filters.limit,
    }


@router.get('/api/entries')
async def entries_json(filters: Annotated[PeopleFilters, Depends()]) -> JSONResponse:
    return JSONResponse(await run_in('store', _listing, filters))


@router.get('', response_class=HTMLResponse)
@router.get('/', response_class=HTMLResponse)
async def page(request: Request) -> HTMLResponse:
    first = await run_in('store', _listing, PeopleFilters(), True)
    type_counts = dict(first['counts'])
    default_tab = str(first['tab'])
    summary = ' · '.join(f'{type_counts[t]} {label.lower()}' for t, label in _TABS if type_counts[t]) or 'none yet'
    return HTMLResponse(
        render_page(
            'people_ui',
            active='people',
            username=nav_username(request),
            entries=first['entries'],
            tabs=_TABS,
            type_counts=type_counts,
            default_tab=default_tab,
            summary=summary,
            total=first['total'],
            page_size=PAGE_SIZE,
            library=first['library'],
            img_base=image_base_url(),
            img_opt=env.image_base_url_raw,
            crop_available=face_crop.available(),
            genders=_GENDERS,
            fetchable_sources=[s.name for s in FETCHABLE_SOURCES],
            present_sources=first['sources'],
            has_unrecorded=first['has_unrecorded'],
        )
    )


def _find_entry(filename: str) -> dict[str, Any] | None:
    row = (
        index_conn()
        .execute("SELECT rel_path, mtime FROM people_images WHERE rel_path LIKE ? ESCAPE '\\' ORDER BY rel_path LIMIT 1", (f'%/{db.like_escape(filename)}',))
        .fetchone()
    )
    if row is None:
        return next((e for e in _list_people() if e['filename'] == filename), None)
    relpath = str(row['rel_path'])
    log = face_crop_log.entry_for(str(Path(env.people_cache_dir) / relpath.rpartition('/')[0]), filename) or {}
    return _entry(relpath, float(row['mtime']), log)


def _find_entry_by_name(name: str, role: str) -> dict[str, Any] | None:
    wanted = name.casefold()
    matches = [e for e in _list_people() if str(e['name']).casefold() == wanted]
    return next((e for e in matches if str(e['role']) == role), None) or (matches[0] if matches else None)


def _scene_rows(entry: dict[str, Any]) -> list[dict[str, Any]] | None:

    if not env.metadata_cache_enabled:
        return None
    scenes = scene_store.scenes_for_person(str(entry.get('name', '')), str(entry.get('role', '')))
    return [{**scene, 'key_quoted': quote(scene['key'], safe='/')} for scene in scenes]


@router.get('/edit', response_class=HTMLResponse)
async def edit_page(request: Request, filename: str = '', name: str = '', role: str = '') -> HTMLResponse:
    if filename:
        entry = await run_in('store', _find_entry, filename)
    elif name:
        entry = await run_in('store', _find_entry_by_name, name, role or 'actor')
    else:
        entry = None
    if entry is None:
        return HTMLResponse(
            '<p style="font-family:system-ui;color:var(--page-text);background:var(--page-bg)">No cached headshot for that person.</p>', status_code=404
        )
    filename = filename or str(entry['filename'])
    relpath = str(entry.get('relpath', filename))
    cached_src = f'{LOCAL_IMAGES}{quote(relpath, safe="/")}?v={int(entry.get("mtime", 0))}'
    scenes = await run_in('store', _scene_rows, entry)
    return HTMLResponse(
        render_page(
            'people_edit',
            active='people',
            username=nav_username(request),
            actor_name=str(entry['name']),
            role=str(entry['role']),
            relpath=relpath,
            origin=str(entry.get('source', '')) or 'unrecorded',
            cached_src=cached_src,
            filename=filename,
            entry=entry,
            sources=[source.name for source in FETCHABLE_SOURCES],
            crop_available=face_crop.available(),
            recorded_sources=list(KNOWN_SOURCES),
            scenes=scenes,
        )
    )


@router.post('/lookup', dependencies=_admin)
async def lookup(request: Request) -> JSONResponse:
    data = await read_json_body(request)
    filename = str(data.get('filename', ''))
    wanted = str(data.get('source', ''))
    entry = await run_in('store', _find_entry, filename) if filename else None
    if entry is None:
        return JSONResponse({'ok': False, 'error': 'unknown filename'}, status_code=404)
    source = next((s for s in FETCHABLE_SOURCES if s.name == wanted), None)
    if source is None:
        return JSONResponse({'ok': False, 'error': 'unknown source'}, status_code=400)
    role: Any = entry['role']
    try:
        hit = await source.find(str(entry['name']), PersonLookupContext(type=role))
    except Exception as err:  # noqa: BLE001 - a failing source is a miss, not a 500
        logger.warn('people-cache', f'{source.name} lookup failed for {entry["name"]}: {err!r}')
        return JSONResponse({'ok': False, 'error': f'{source.name} lookup failed'}, status_code=502)
    if hit is None or not hit.url:
        return JSONResponse({'ok': False, 'error': f'{source.name} has no image for "{entry["name"]}"'}, status_code=404)
    logger.info('people-cache', f'{source.name} offered an image for {entry["name"]}')
    return JSONResponse({'ok': True, 'url': hit.url, 'gender': hit.gender or '', 'source': source.name})


@router.post('/bulk-fetch', dependencies=_admin)
async def bulk_fetch(request: Request) -> Response:
    data = await read_json_body(request)
    wanted = str(data.get('source', ''))
    raw = data.get('filenames')
    filenames = [str(f) for f in raw if isinstance(f, str)] if isinstance(raw, list) else []
    source = next((s for s in FETCHABLE_SOURCES if s.name == wanted), None)
    if source is None:
        return JSONResponse({'ok': False, 'error': 'unknown source'}, status_code=400)
    if not filenames:
        return JSONResponse({'ok': False, 'error': 'no people selected'}, status_code=400)

    truncated = max(0, len(filenames) - _BULK_MAX)
    known = {e['filename']: e for e in await run_in('store', _list_people)}
    stream = _bulk_stream(source, filenames[:_BULK_MAX], known, truncated)
    return StreamingResponse(stream, media_type='application/x-ndjson')


async def _fetch_into_cache(source: PersonSource, filename: str, entry: dict[str, Any] | None) -> tuple[str, str]:
    if entry is None:
        return 'failed', filename
    name = str(entry['name'])
    role: Any = entry['role']
    try:
        hit = await source.find(name, PersonLookupContext(type=role))
    except Exception as err:  # noqa: BLE001 - one person failing must not abort the batch
        logger.warn('people-cache', f'{source.name} threw for {name}: {err!r}')
        return 'failed', name
    if hit is None or not hit.url:
        return 'missed', name
    cached = await cache_photo(hit.url, name, role, _gender_of(str(entry['gender'])), replace=True, crop=bool(entry['cropped']), source=source.name)
    if cached is None:
        return 'failed', name
    await run_in('store', scene_store.flag_people_changed, name)
    return 'updated', name


async def _bulk_stream(source: PersonSource, filenames: list[str], known: dict[str, dict[str, Any]], truncated: int) -> AsyncIterator[str]:
    total = len(filenames)
    sem = asyncio.Semaphore(_BULK_CONCURRENCY)
    tally = {'updated': 0, 'missed': 0, 'failed': 0}
    errors = 0
    queue: asyncio.Queue[tuple[str, str] | None] = asyncio.Queue()

    async def _one(filename: str) -> None:
        nonlocal errors
        try:
            async with sem:
                outcome, name = await _fetch_into_cache(source, filename, known.get(filename))
        except Exception as err:  # noqa: BLE001 - one person must not truncate the batch or fake a clean finish
            logger.warn('people-cache', f'{source.name} raised for {filename}: {err!r}')
            errors += 1
            outcome, name = 'failed', filename
        tally[outcome] += 1
        await queue.put((outcome, name))

    async def _run() -> None:
        try:
            await asyncio.gather(*(_one(f) for f in filenames), return_exceptions=True)
        finally:
            await queue.put(None)

    runner = asyncio.create_task(_run())
    yield json.dumps({'source': source.name, 'total': total}) + '\n'
    done = 0
    try:
        while (item := await queue.get()) is not None:
            done += 1
            yield json.dumps({'done': done, 'total': total, 'outcome': item[0], 'name': item[1]}) + '\n'
    finally:
        runner.cancel()
    logger.info(
        'people-cache', f'bulk fetch from {source.name}: {tally["updated"]} updated, {tally["missed"]} not found, {tally["failed"]} failed, {errors} errored'
    )
    yield json.dumps({'ok': errors == 0, 'source': source.name, **tally, 'errors': errors, 'truncated': truncated}) + '\n'


def _relabel_source(entry: dict[str, Any], source: str) -> bool:
    if source == str(entry.get('source', '')):
        return False
    directory = str(Path(env.people_cache_dir) / str(entry['relpath']).rpartition('/')[0])
    if not face_crop_log.update(directory, str(entry['filename']), source=source):
        logger.warn('people-cache', f'cannot relabel {entry["filename"]} — it has no crop-log entry to carry the source')
        return False
    logger.info('people-cache', f'relabelled {entry["filename"]} source: {entry.get("source") or "unrecorded"} -> {source or "unrecorded"}')
    return True


@router.post('/save', dependencies=_admin)
async def save(request: Request) -> JSONResponse:
    data = await read_json_body(request)
    filename = str(data.get('filename', ''))
    upstream = str(data.get('upstream_url', '')).strip()
    picked = str(data.get('source', ''))
    relabel = str(data.get('recorded_source', ''))
    wants_crop = bool(data.get('cropped'))
    if not filename:
        return JSONResponse({'ok': False, 'error': 'missing filename'}, status_code=400)
    entry = await run_in('store', _find_entry, filename)
    if entry is None:
        return JSONResponse({'ok': False, 'error': 'unknown filename'}, status_code=404)
    if not upstream:
        return JSONResponse({'ok': False, 'error': 'an upstream URL is required to re-cache the image'}, status_code=400)
    if relabel and relabel not in KNOWN_SOURCES:
        return JSONResponse({'ok': False, 'error': f'unknown source "{relabel}"'}, status_code=400)
    relabelled = await run_in('store', _relabel_source, entry, relabel)
    if upstream == entry['upstream_url'] and wants_crop == entry['cropped']:
        return JSONResponse({'ok': True, 'changed': relabelled})
    role: Any = entry['role']
    source = picked if any(s.name == picked for s in FETCHABLE_SOURCES) else ''
    cached = await cache_photo(upstream, str(entry['name']), role, _gender_of(str(entry['gender'])), replace=True, crop=wants_crop, source=source)
    if cached is None:
        return JSONResponse({'ok': False, 'error': 'could not download or store that image'}, status_code=400)
    flagged = await run_in('store', scene_store.flag_people_changed, str(entry['name']))
    logger.info('people-cache', f'edited {filename}: upstream={upstream} cropped={wants_crop}; {len(flagged)} scene(s) flagged to re-push')
    return JSONResponse({'ok': True, 'changed': True, 'scenes': len(flagged)})


@router.post('/restore', dependencies=_admin)
async def restore(request: Request) -> JSONResponse:
    data = await read_json_body(request)
    filename = str(data.get('filename', ''))
    if not filename:
        return JSONResponse({'ok': False, 'error': 'missing filename'}, status_code=400)
    ok = await restore_original(filename)
    return JSONResponse({'ok': ok})


@router.post('/purge', dependencies=_admin)
async def purge_file(request: Request) -> JSONResponse:
    data = await read_json_body(request)
    filename = str(data.get('filename', ''))
    if not filename:
        return JSONResponse({'ok': False, 'error': 'missing filename'}, status_code=400)
    return JSONResponse({'ok': await run_in('fs', purge, filename)})


@router.post('/gender', dependencies=_admin)
async def gender(request: Request) -> JSONResponse:
    data = await read_json_body(request)
    filename = str(data.get('filename', ''))
    new_gender = str(data.get('gender', ''))
    if not filename:
        return JSONResponse({'ok': False, 'error': 'missing filename'}, status_code=400)
    if new_gender not in get_args(Gender):
        return JSONResponse({'ok': False, 'error': 'invalid gender'}, status_code=400)
    new_filename = await run_in('fs', set_gender, filename, new_gender)
    return JSONResponse({'ok': new_filename is not None, 'filename': new_filename})
