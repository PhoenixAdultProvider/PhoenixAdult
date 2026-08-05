from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from phoenixadult.config import image_base_url
from phoenixadult.config.env import env
from phoenixadult.routes import nav_username, read_json_body, render_page
from phoenixadult.utils.auth.user_auth import admin_auth_guard, csrf_guard, user_auth_guard
from phoenixadult.utils.cache import scene_store
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.images import face_crop, face_crop_log
from phoenixadult.utils.images.ext import IMAGE_EXTS
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.people.cache import _ORIGINALS_DIR, _index_conn, cache_photo, people_cache_dir, purge, restore_original, set_gender
from phoenixadult.utils.people.image_source import KNOWN_SOURCES
from phoenixadult.utils.people.sources import ALL_SOURCES
from phoenixadult.utils.people.sources.localStorage import local_storage_source
from phoenixadult.utils.people.types import Gender, PersonLookupContext, PersonSource, parse_person_filename

router = APIRouter(dependencies=[Depends(user_auth_guard), Depends(csrf_guard)])
_admin = [Depends(admin_auth_guard)]

FETCHABLE_SOURCES = [source for source in ALL_SOURCES if source.name != local_storage_source.name]
_BULK_CONCURRENCY = 3
_BULK_MAX = 250

_ROLES = ('actor', 'director', 'producer')
_GENDERS = [('', 'gn', 'None'), ('male', 'gm', 'Male'), ('female', 'gf', 'Female'), ('trans', 'gt', 'Trans')]
_ROLE_CSS = {'actor': 'r-actor', 'director': 'r-director', 'producer': 'r-producer'}
_TABS = [
    ('directors', 'Directors'),
    ('producers', 'Producers'),
    ('actors-female', 'Female Actors'),
    ('actors-male', 'Male Actors'),
    ('actors-trans', 'Trans Actors'),
    ('actors-unknown', 'Unknown Actors'),
]


def _parse_filename(filename: str) -> tuple[str, str, str] | None:
    role, slug, gender = parse_person_filename(filename)
    if role not in _ROLES or not slug:
        return None
    return role, slug.replace('-', ' ').title(), gender


def _entry(relpath: str, mtime: float, log: dict[str, Any]) -> dict[str, Any] | None:
    subpath, _, filename = relpath.rpartition('/')
    parsed = _parse_filename(filename)
    if not parsed:
        return None
    role, name, gender = parsed
    return {
        'name': log.get('name') or name,
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


def _list_people(directory: str) -> list[dict[str, Any]]:
    rows = _index_conn().execute('SELECT rel_path, mtime FROM people_images ORDER BY rel_path').fetchall()
    if not rows:
        return _list_people_files(directory)
    logs = face_crop_log.entries_by_path()
    out = [_entry(str(r['rel_path']), float(r['mtime']), logs.get(str(r['rel_path']), {})) for r in rows]
    kept = [e for e in out if e is not None]
    kept.sort(key=lambda e: e['mtime'], reverse=True)
    return kept


def _list_people_files(directory: str) -> list[dict[str, Any]]:
    root = Path(directory)
    if not root.exists():
        return []
    subdirs = sorted({f.parent for f in root.rglob('*') if f.is_file() and not f.name.startswith('.') and f.suffix.lower() in IMAGE_EXTS})
    out: list[dict[str, Any]] = []
    for sd in subdirs:
        subpath = sd.relative_to(root).as_posix()
        if subpath == _ORIGINALS_DIR or subpath.startswith(f'{_ORIGINALS_DIR}/'):
            continue
        by_file = {e.get('filename'): e for e in face_crop_log.recent(str(sd))}
        for f in sorted(sd.iterdir()):
            if not f.is_file() or f.name.startswith('.') or f.suffix.lower() not in IMAGE_EXTS:
                continue
            try:
                mtime = f.stat().st_mtime
            except OSError:
                mtime = 0.0
            entry = _entry(f'{subpath}/{f.name}', mtime, by_file.get(f.name) or {})
            if entry is not None:
                out.append(entry)
    out.sort(key=lambda e: e['mtime'], reverse=True)
    return out


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
        'local_src': f'/images/local/{quote(relpath, safe="/")}?v={int(entry.get("mtime", 0))}',
        'upstream_quoted': quote(str(entry.get('upstream_url', '')), safe=''),
        'search_key': name.casefold(),
        'single': len(name.split()) == 1,
    }


@router.get('', response_class=HTMLResponse)
@router.get('/', response_class=HTMLResponse)
async def page(request: Request) -> HTMLResponse:
    entries = await run_in('store', _list_people, people_cache_dir())
    type_counts = {t: sum(1 for e in entries if e['type'] == t) for t, _ in _TABS}
    default_tab = next((t for t, _ in _TABS if type_counts[t]), _TABS[0][0])
    summary = ' · '.join(f'{type_counts[t]} {label.lower()}' for t, label in _TABS if type_counts[t]) or 'none yet'
    return HTMLResponse(
        render_page(
            'people_ui',
            active='people',
            username=nav_username(request),
            entries=[_display_entry(e) for e in entries],
            tabs=_TABS,
            type_counts=type_counts,
            default_tab=default_tab,
            summary=summary,
            img_base=image_base_url(),
            img_opt=env.image_base_url_raw,
            crop_available=face_crop.available(),
            genders=_GENDERS,
            fetchable_sources=[s.name for s in FETCHABLE_SOURCES],
            present_sources=sorted({str(e['source']) for e in entries if e['source']}, key=str.casefold),
            has_unrecorded=any(not e['source'] for e in entries),
        )
    )


def _find_entry(filename: str) -> dict[str, Any] | None:
    return next((e for e in _list_people(people_cache_dir()) if e['filename'] == filename), None)


def _find_entry_by_name(name: str, role: str) -> dict[str, Any] | None:
    wanted = name.casefold()
    matches = [e for e in _list_people(people_cache_dir()) if str(e['name']).casefold() == wanted]
    return next((e for e in matches if str(e['role']) == role), None) or (matches[0] if matches else None)


def _scene_rows(entry: dict[str, Any]) -> list[dict[str, Any]] | None:
    from phoenixadult.utils import cache as metadata_cache

    if not metadata_cache.enabled():
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
    cached_src = f'/images/local/{quote(relpath, safe="/")}?v={int(entry.get("mtime", 0))}'
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
    known = {e['filename']: e for e in await run_in('store', _list_people, people_cache_dir())}
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
    queue: asyncio.Queue[tuple[str, str] | None] = asyncio.Queue()

    async def _one(filename: str) -> None:
        async with sem:
            outcome, name = await _fetch_into_cache(source, filename, known.get(filename))
        tally[outcome] += 1
        await queue.put((outcome, name))

    async def _run() -> None:
        try:
            await asyncio.gather(*(_one(f) for f in filenames))
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
    logger.info('people-cache', f'bulk fetch from {source.name}: {tally["updated"]} updated, {tally["missed"]} not found, {tally["failed"]} failed')
    yield json.dumps({'ok': True, 'source': source.name, **tally, 'truncated': truncated}) + '\n'


def _relabel_source(entry: dict[str, Any], source: str) -> bool:
    if source == str(entry.get('source', '')):
        return False
    directory = str(Path(people_cache_dir()) / str(entry['relpath']).rpartition('/')[0])
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
    if new_gender not in ('', 'male', 'female', 'trans'):
        return JSONResponse({'ok': False, 'error': 'invalid gender'}, status_code=400)
    new_filename = await run_in('fs', set_gender, filename, new_gender)
    return JSONResponse({'ok': new_filename is not None, 'filename': new_filename})
