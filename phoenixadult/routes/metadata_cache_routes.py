from __future__ import annotations

import asyncio
import html
import json
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from phoenixadult.config.env import env
from phoenixadult.registry import find_site
from phoenixadult.routes import nav_username, read_json_body, render_nav
from phoenixadult.routes.provider_router import service_for
from phoenixadult.utils import cache as metadata_cache
from phoenixadult.utils.auth.user_auth import csrf_guard, user_auth_guard
from phoenixadult.utils.cache import scene_store
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.helpers.helpers import load_data
from phoenixadult.utils.logging.logger import logger

router = APIRouter(dependencies=[Depends(user_auth_guard), Depends(csrf_guard)])

_TEMPLATE: str = load_data(__file__, 'metadata_cache', kind='html')
_EDIT_TEMPLATE: str = load_data(__file__, 'metadata_edit', kind='html')

_SORT_KEYS = ('title', 'studio', 'tagline', 'release_date', 'data18_id', 'updated_at')
_EDIT_TEXT = ('title', 'titleSort', 'summary', 'tagline', 'studio', 'originallyAvailableAt', 'data18_id', 'data18_type')
_EDIT_TAGS = ('Genre', 'Collection', 'Country', 'Role', 'Director', 'Producer')


def _json_attr(value: object) -> str:
    return json.dumps(value).replace('<', '\\u003c')


@router.get('', response_class=HTMLResponse)
@router.get('/', response_class=HTMLResponse)
async def page(request: Request) -> HTMLResponse:
    (entries, total), dup_keys, studios, facets = await asyncio.gather(
        run_in('store', metadata_cache.entries_page),
        run_in('store', metadata_cache.stale_duplicate_entries),
        run_in('store', metadata_cache.studios),
        run_in('store', metadata_cache.facets),
    )
    state = 'On' if env.metadata_cache_enabled else 'Off (set METADATA_CACHE_ENABLE=true to enable)'
    body = (
        _TEMPLATE.replace('__NAV__', render_nav('metadata', nav_username(request)))
        .replace('__STATE__', state)
        .replace('__ENTRIES_JSON__', _json_attr(entries))
        .replace('__TOTAL__', json.dumps(total))
        .replace('__STUDIOS__', _json_attr(studios))
        .replace('__FACETS__', _json_attr(facets))
        .replace('__DUP_KEYS__', _json_attr(dup_keys))
    )
    return HTMLResponse(body)


@router.get('/edit', response_class=HTMLResponse)
async def edit_page(request: Request, key: str = '') -> HTMLResponse:
    loaded = await run_in('store', metadata_cache.load_for_edit, key) if '/' in key else None
    if loaded is None:
        return HTMLResponse('<p style="font-family:system-ui;color:#e2e8f0;background:#0f1117">No snapshot for that key.</p>', status_code=404)
    md = (loaded.get('MediaContainer') or {}).get('Metadata') or [{}]
    subtitle = f'<code id="subKey">{html.escape(key)}</code>'
    from phoenixadult.clients.aggregators.data18 import mapping_slug

    slug = mapping_slug(str(md[0].get('title') or ''), str(md[0].get('tagline') or md[0].get('studio') or '') or None) or ''
    body = (
        _EDIT_TEMPLATE.replace('__NAV__', render_nav('metadata', nav_username(request)))
        .replace('__SUBTITLE__', subtitle)
        .replace('__KEY__', _json_attr(key))
        .replace('__MAPPING_SLUG__', _json_attr(slug))
        .replace('__METADATA__', _json_attr(md[0]))
    )
    return HTMLResponse(body)


@router.post('/save')
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
    if not str(fields.get('title', '')).strip():
        return JSONResponse({'ok': False, 'error': 'title is required'}, status_code=400)
    moved = await metadata_cache.save_edits(key, fields)
    if moved is None:
        return JSONResponse({'ok': False, 'error': 'snapshot not written — check the title and METADATA_CACHE_ENABLE'}, status_code=400)
    return JSONResponse({'ok': True, 'key': moved})


@router.post('/refresh')
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


@router.post('/refresh-bulk')
async def refresh_bulk(request: Request) -> JSONResponse:
    data = await read_json_body(request)
    keys = data.get('keys')
    if not isinstance(keys, list) or not keys or not all(isinstance(k, str) and '/' in k for k in keys):
        return JSONResponse({'ok': False, 'error': 'bad keys'}, status_code=400)

    targets = await run_in('store', lambda: [scene_store.scrape_target(key) for key in keys])
    queued = 0
    skipped = 0
    for target in targets:
        site = find_site(target['site']) if target else None
        resolved = service_for(site.provider_id) if site else None
        if target is None or resolved is None:
            skipped += 1
            continue
        provider, metadata_service = resolved
        metadata_service.drop_memo(target['rating_key'], provider)
        if metadata_service.queue_snapshot(target['rating_key'], provider, None, force=True, rescrape=True):
            queued += 1
        else:
            skipped += 1
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
    return JSONResponse({'ok': True, 'key': snap['key'], 'updated_at': snap['updated_at'], 'metadata': md[0]})


@router.get('/actors')
async def actors(query: str = Query('', alias='q'), limit: int = Query(50, ge=1, le=200)) -> JSONResponse:
    return JSONResponse({'actors': await run_in('store', metadata_cache.actor_suggestions, query, limit)})


@router.get('/state')
async def state() -> JSONResponse:
    return JSONResponse({'token': await run_in('store', metadata_cache.change_token)})


@router.get('/entries')
async def entries_json(
    studio: str = '',
    query: str = Query('', alias='q'),
    year: str = '',
    month: str = '',
    day: str = '',
    tagline: str = '',
    collection: str = '',
    data18: str = '',
    actor: str = '',
    genre: str = '',
    cast: str = '',
    director: str = '',
    producer: str = '',
    provider: str = '',
    dups: int = Query(0, ge=0, le=2),
    sort: str = 'updated_at',
    direction: str = Query('desc', alias='dir'),
    limit: int = Query(500, ge=0, le=1000),
    offset: int = Query(0, ge=0),
) -> JSONResponse:
    sort = sort if sort in _SORT_KEYS else 'updated_at'
    direction = direction if direction in ('asc', 'desc') else 'desc'
    dup_keys = await run_in('store', metadata_cache.stale_duplicate_entries)
    show_paths = await run_in('store', metadata_cache.content_duplicate_entries) if dups == 2 else dup_keys
    scope: dict[str, Any] = {
        'studio': studio,
        'query': query,
        'year': year,
        'month': month,
        'day': day,
        'tagline': tagline,
        'collection': collection,
        'data18': data18,
        'actor': actor,
        'genre': genre,
        'cast': cast,
        'director': director,
        'producer': producer,
        'provider': provider,
        'dup_paths': show_paths if dups else None,
    }
    (entries, total), studios, facets = await asyncio.gather(
        run_in(
            'store',
            lambda: metadata_cache.entries_page(
                studio=studio,
                query=query,
                year=year,
                month=month,
                day=day,
                tagline=tagline,
                collection=collection,
                data18=data18,
                actor=actor,
                genre=genre,
                cast=cast,
                director=director,
                producer=producer,
                provider=provider,
                dups_only=bool(dups),
                dup_paths=show_paths,
                sort=sort,
                direction=direction,
                limit=limit if limit > 0 else -1,
                offset=offset,
            ),
        ),
        run_in('store', lambda: metadata_cache.studios(**scope)),
        run_in('store', lambda: metadata_cache.facets(**scope)),
    )
    return JSONResponse({'entries': entries, 'dup_keys': dup_keys, 'total': total, 'studios': studios, 'facets': facets})


@router.post('/purge')
async def purge(request: Request) -> JSONResponse:
    data = await read_json_body(request)
    key = str(data.get('key', ''))
    if '/' not in key:
        return JSONResponse({'ok': False, 'error': 'bad key'}, status_code=400)
    ok = await run_in('store', metadata_cache.purge, key)
    return JSONResponse({'ok': ok})


@router.post('/purge-bulk')
async def purge_bulk(request: Request) -> JSONResponse:
    data = await read_json_body(request)
    keys = data.get('keys')
    if not isinstance(keys, list) or not keys or not all(isinstance(k, str) and '/' in k for k in keys):
        return JSONResponse({'ok': False, 'error': 'bad keys'}, status_code=400)
    purged = await run_in('store', lambda: sum(1 for key in keys if metadata_cache.purge(key)))
    return JSONResponse({'ok': True, 'purged': purged})


@router.post('/purge-duplicates')
async def purge_duplicates() -> JSONResponse:
    return JSONResponse({'ok': True, 'purged': await run_in('store', metadata_cache.purge_duplicates)})


@router.post('/prune-names')
async def prune_names() -> JSONResponse:
    pruned = await run_in('store', scene_store.prune_orphan_names)
    return JSONResponse({'ok': True, 'pruned': pruned, 'total': sum(pruned.values())})
