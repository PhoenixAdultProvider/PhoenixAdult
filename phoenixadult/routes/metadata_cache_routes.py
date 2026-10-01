from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from phoenixadult.clients import get_client
from phoenixadult.config.env import env
from phoenixadult.registry import find_site
from phoenixadult.routes import nav_username, read_json_body, render_page
from phoenixadult.routes.provider_router import service_for
from phoenixadult.utils.auth.user_auth import admin_auth_guard, csrf_guard, user_auth_guard
from phoenixadult.utils.cache import duplicates as cache_duplicates
from phoenixadult.utils.cache import integrity as cache_integrity
from phoenixadult.utils.cache import layout as cache_layout
from phoenixadult.utils.cache import listing as cache_listing
from phoenixadult.utils.cache import metadata as metadata_cache
from phoenixadult.utils.cache import scene_store
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.helpers.data18 import mapping_slug
from phoenixadult.utils.http.ssrf_guard import ensure_fetchable_url
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.processors.scene_link import resolve_source_link

router = APIRouter(dependencies=[Depends(user_auth_guard), Depends(csrf_guard)])
_admin = [Depends(admin_auth_guard)]

PAGE_SIZE = 200

_SORT_KEYS = ('title', 'studio', 'tagline', 'release_date', 'data18_id', 'updated_at')
_EDIT_TEXT = ('title', 'titleSort', 'summary', 'tagline', 'studio', 'originallyAvailableAt', 'data18_id', 'data18_type')
_EDIT_TAGS = ('Genre', 'Collection', 'Country', 'Role', 'Director', 'Producer')


@router.get('', response_class=HTMLResponse)
@router.get('/', response_class=HTMLResponse)
async def page(request: Request) -> HTMLResponse:
    def _bundle() -> tuple[tuple[list[cache_listing.UiEntry], int], list[str], list[str], dict[str, Any]]:
        return (
            cache_listing.entries_page(limit=PAGE_SIZE),
            cache_duplicates.stale_duplicate_entries(),
            cache_listing.studios(),
            cache_listing.facets(),
        )

    (entries, total), dup_keys, studios, facets = await run_in('store', _bundle)
    status = 'On' if env.metadata_cache_enabled else 'Off (set METADATA_CACHE_ENABLE=true to enable)'
    return HTMLResponse(
        render_page(
            'metadata_cache',
            active='metadata',
            username=nav_username(request),
            status=status,
            entries=entries,
            total=total,
            studios=studios,
            facets=facets,
            dup_keys=dup_keys,
            page_size=PAGE_SIZE,
        )
    )


def _source_context(identity: tuple[str, str] | None, md: dict[str, Any]) -> tuple[str | None, str | None, Any]:
    stored = md.get('sourceRef') or {}
    if stored.get('url') or stored.get('data') is not None:
        kind = str(stored.get('kind') or ('page' if stored.get('url') else 'json'))
        kind = 'scene' if kind == 'page' else kind
        url = stored.get('url') if kind in ('scene', 'listing') else None
        return kind, url, stored.get('data')
    if identity is None:
        return None, None, None
    source = resolve_source_link(identity[1], find_site(identity[0]))
    return source.kind, source.url if source.kind in ('scene', 'listing') else None, source.payload


@router.get('/edit', response_class=HTMLResponse)
async def edit_page(request: Request, key: str = '') -> HTMLResponse:
    loaded = await run_in('store', metadata_cache.load_for_edit, key) if '/' in key else None
    if loaded is None:
        return HTMLResponse('<p style="font-family:system-ui;color:#e2e8f0;background:#0f1117">No snapshot for that key.</p>', status_code=404)
    md = (loaded.get('MediaContainer') or {}).get('Metadata') or [{}]

    slug = mapping_slug(str(md[0].get('title') or ''), str(md[0].get('tagline') or md[0].get('studio') or '') or None) or ''
    identity = await run_in('store', scene_store.identity_for, key)
    locks = await run_in('store', scene_store.locks, cache_layout.scene_hash_for(*identity)) if identity else {'fields': [], 'imagesLocked': False}
    source_kind, source_url, source_data = _source_context(identity, md[0])
    return HTMLResponse(
        render_page(
            'metadata_edit',
            active='metadata',
            username=nav_username(request),
            key=key,
            mapping_slug=slug,
            metadata=md[0],
            locks=locks,
            source_kind=source_kind,
            source_url=source_url,
            source_json=source_data,
        )
    )


@router.get('/source-json', dependencies=_admin)
async def source_json(key: str = '') -> JSONResponse:
    if '/' not in key:
        return JSONResponse({'ok': False, 'error': 'bad key'}, status_code=400)
    identity = await run_in('store', scene_store.identity_for, key)
    if identity is None:
        return JSONResponse({'ok': False, 'error': 'unknown key'}, status_code=404)
    loaded = await run_in('store', metadata_cache.load_for_edit, key)
    md = ((loaded or {}).get('MediaContainer') or {}).get('Metadata') or [{}]
    stored = (md[0].get('sourceRef') or {}).get('data')
    if stored is not None:
        return JSONResponse({'ok': True, 'json': stored})
    site = find_site(identity[0])
    source = resolve_source_link(identity[1], site)
    if source.payload is not None:
        return JSONResponse({'ok': True, 'json': source.payload})
    if source.kind != 'api' or not source.url:
        return JSONResponse({'ok': False, 'error': 'no source payload for this scene'}, status_code=400)
    try:
        await ensure_fetchable_url(source.url)
    except ValueError as err:
        return JSONResponse({'ok': False, 'error': str(err)}, status_code=400)
    client = get_client(site.scraper_config.type) if site else None
    data = await client.fetch_json(source.url) if client else None
    if data is None:
        return JSONResponse({'ok': False, 'error': 'the source API did not return JSON (it may need auth or be rate-limited)'}, status_code=502)
    return JSONResponse({'ok': True, 'json': data})


@router.post('/save', dependencies=_admin)
async def save(request: Request) -> JSONResponse:
    data = await read_json_body(request)
    key = str(data.get('key', ''))
    if '/' not in key:
        return JSONResponse({'ok': False, 'error': 'bad key'}, status_code=400)
    fields: dict[str, Any] = {name: data[name] for name in _EDIT_TEXT if name in data}
    for name in _EDIT_TAGS:
        if isinstance(data.get(name), list):
            fields[name] = data[name]
    if isinstance(data.get('Image'), list):
        fields['Image'] = [image for image in data['Image'] if isinstance(image, dict)]
    if isinstance(data.get('lockedFields'), list):
        fields['lockedFields'] = data['lockedFields']
    if 'imagesLocked' in data:
        fields['imagesLocked'] = bool(data['imagesLocked'])
    if not str(fields.get('title', '')).strip():
        return JSONResponse({'ok': False, 'error': 'title is required'}, status_code=400)
    moved = await metadata_cache.save_edits(key, fields)
    if moved is None:
        return JSONResponse({'ok': False, 'error': 'snapshot not written — check the title and METADATA_CACHE_ENABLE'}, status_code=400)
    return JSONResponse({'ok': True, 'key': moved})


@router.post('/refresh', dependencies=_admin)
async def refresh(request: Request) -> JSONResponse:
    data = await read_json_body(request)
    key = str(data.get('key', ''))
    if '/' not in key:
        return JSONResponse({'ok': False, 'error': 'bad key'}, status_code=400)

    target = await run_in('store', scene_store.scrape_target, key)
    if target is None:
        return JSONResponse({'ok': False, 'error': 'no scene stored for that key'}, status_code=404)

    site = find_site(target['site'])
    resolved = service_for(site.provider_id) if site else None
    if resolved is None:
        return JSONResponse({'ok': False, 'error': f'no provider serving site "{target["site"]}"'}, status_code=400)

    provider, metadata_service = resolved
    metadata_service.drop_memo(target['rating_key'], provider)
    queued = metadata_service.queue_snapshot(target['rating_key'], provider, None, force=True, rescrape=True)
    snap = await run_in('store', scene_store.snapshot_state, target['site'], target['cur_id'])
    return JSONResponse(
        {
            'ok': True,
            'queued': queued,
            'site': target['site'],
            'cur_id': target['cur_id'],
            'queue_key': f'{provider.id}:{target["rating_key"]}',
            'updated_at': (snap or {}).get('updated_at', ''),
        }
    )


@router.post('/refresh-bulk', dependencies=_admin)
async def refresh_bulk(request: Request) -> JSONResponse:
    data = await read_json_body(request)
    keys = data.get('keys')
    if not isinstance(keys, list) or not keys or not all(isinstance(k, str) and '/' in k for k in keys):
        return JSONResponse({'ok': False, 'error': 'bad keys'}, status_code=400)

    from phoenixadult.services.metadata_service import queue_label

    def _targets() -> list[tuple[dict[str, Any] | None, str]]:
        found = [scene_store.scrape_target(key) for key in keys]
        return [(t, queue_label(str(t['rating_key'])) if t else '') for t in found]

    targets = await run_in('store', _targets)
    queued = 0
    skipped = 0
    for target, label in targets:
        site = find_site(target['site']) if target else None
        resolved = service_for(site.provider_id) if site else None
        if target is None or resolved is None:
            skipped += 1
            continue
        provider, metadata_service = resolved
        metadata_service.drop_memo(target['rating_key'], provider)
        if metadata_service.queue_snapshot(target['rating_key'], provider, None, label=label, force=True, rescrape=True):
            queued += 1
        else:
            skipped += 1
        await asyncio.sleep(0)
    logger.info('meta-cache', f'Refresh requested for {len(keys)} snapshot(s) — {queued} queued, {skipped} skipped')
    return JSONResponse({'ok': True, 'queued': queued, 'skipped': skipped})


@router.get('/snapshot')
async def snapshot(site: str = '', cur_id: str = '') -> JSONResponse:
    if not site or not cur_id:
        return JSONResponse({'ok': False, 'error': 'site and cur_id are required'}, status_code=400)
    snap = await run_in('store', scene_store.snapshot_state, site, cur_id)
    if snap is None:
        return JSONResponse({'ok': False, 'error': 'not snapshotted'}, status_code=404)
    loaded = await run_in('store', metadata_cache.load_for_edit, snap['key'])
    md = ((loaded or {}).get('MediaContainer') or {}).get('Metadata') or [{}]
    locks = await run_in('store', scene_store.locks, cache_layout.scene_hash_for(site, cur_id))
    return JSONResponse({'ok': True, 'key': snap['key'], 'updated_at': snap['updated_at'], 'metadata': md[0], 'locks': locks})


@router.get('/actors')
async def actors(query: str = Query('', alias='q'), limit: int = Query(50, ge=1, le=200)) -> JSONResponse:
    return JSONResponse({'actors': await run_in('store', scene_store.actor_names, query, limit)})


@router.get('/state')
async def state() -> JSONResponse:
    return JSONResponse({'token': await run_in('store', cache_listing.change_token)})


_SCOPE_FIELDS = (
    'studio',
    'query',
    'year',
    'month',
    'day',
    'tagline',
    'collection',
    'data18',
    'actor',
    'genre',
    'cast',
    'director',
    'producer',
    'provider',
)


@dataclass
class EntryFilters:
    studio: str = ''
    query: str = Query('', alias='q')
    year: str = ''
    month: str = ''
    day: str = ''
    tagline: str = ''
    collection: str = ''
    data18: str = ''
    actor: str = ''
    genre: str = ''
    cast: str = ''
    director: str = ''
    producer: str = ''
    provider: str = ''
    dups: int = Query(0, ge=0, le=2)
    broken: int = Query(0, ge=0, le=1)
    sort: str = 'updated_at'
    direction: str = Query('desc', alias='dir')
    limit: int = Query(PAGE_SIZE, ge=0, le=1000)
    offset: int = Query(0, ge=0)

    def __post_init__(self) -> None:
        if self.sort not in _SORT_KEYS:
            self.sort = 'updated_at'
        if self.direction not in ('asc', 'desc'):
            self.direction = 'desc'

    def scope(self, dup_paths: list[str] | None) -> dict[str, Any]:
        return {name: getattr(self, name) for name in _SCOPE_FIELDS} | {'dup_paths': dup_paths}


def _restricted_paths(filters: EntryFilters, dup_paths: list[str]) -> list[str] | None:
    picked = [set(dup_paths)] if filters.dups else []
    if filters.broken:
        picked.append(set(cache_integrity.missing_image_entries()))
    if not picked:
        return None

    return sorted(set.intersection(*picked))


@router.get('/entries')
async def entries_json(filters: Annotated[EntryFilters, Depends()]) -> JSONResponse:
    def _bundle() -> dict[str, Any]:
        dup_keys = cache_duplicates.stale_duplicate_entries()
        show_paths = cache_duplicates.content_duplicate_entries() if filters.dups == 2 else dup_keys
        restrict = _restricted_paths(filters, show_paths)
        scope = filters.scope(restrict)
        entries, total = cache_listing.entries_page(
            **{k: v for k, v in scope.items() if k != 'dup_paths'},
            dups_only=restrict is not None,
            dup_paths=restrict or [],
            sort=filters.sort,
            direction=filters.direction,
            limit=filters.limit if filters.limit > 0 else -1,
            offset=filters.offset,
        )
        return {
            'entries': entries,
            'dup_keys': dup_keys,
            'total': total,
            'studios': cache_listing.studios(**scope),
            'facets': cache_listing.facets(**scope),
        }

    return JSONResponse(await run_in('store', _bundle))


@router.post('/purge', dependencies=_admin)
async def purge(request: Request) -> JSONResponse:
    data = await read_json_body(request)
    key = str(data.get('key', ''))
    if '/' not in key:
        return JSONResponse({'ok': False, 'error': 'bad key'}, status_code=400)
    ok = await run_in('store', cache_listing.purge, key)
    return JSONResponse({'ok': ok})


@router.post('/purge-bulk', dependencies=_admin)
async def purge_bulk(request: Request) -> JSONResponse:
    data = await read_json_body(request)
    keys = data.get('keys')
    if not isinstance(keys, list) or not keys or not all(isinstance(k, str) and '/' in k for k in keys):
        return JSONResponse({'ok': False, 'error': 'bad keys'}, status_code=400)
    purged = await run_in('store', lambda: sum(1 for key in keys if cache_listing.purge(key)))
    return JSONResponse({'ok': True, 'purged': purged})


@router.post('/purge-duplicates', dependencies=_admin)
async def purge_duplicates() -> JSONResponse:
    return JSONResponse({'ok': True, 'purged': await run_in('store', cache_listing.purge_duplicates)})


@router.post('/prune-names', dependencies=_admin)
async def prune_names() -> JSONResponse:
    pruned = await run_in('store', scene_store.prune_orphan_names)
    return JSONResponse({'ok': True, 'pruned': pruned, 'total': sum(pruned.values())})
