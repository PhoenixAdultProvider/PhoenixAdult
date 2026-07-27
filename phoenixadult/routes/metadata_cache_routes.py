from __future__ import annotations

import html
import json
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from phoenixadult.config.env import env
from phoenixadult.routes import read_json_body
from phoenixadult.utils import cache as metadata_cache
from phoenixadult.utils.auth.env_auth import csrf_guard, env_auth_guard
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.helpers.helpers import load_data

router = APIRouter(dependencies=[Depends(env_auth_guard), Depends(csrf_guard)])

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
    entries, total = await run_in('store', metadata_cache.entries_page)
    dup_keys = await run_in('store', metadata_cache.duplicate_entries)
    studios = await run_in('store', metadata_cache.studios)
    facets = await run_in('store', metadata_cache.facets)
    token = request.query_params.get('token', '')
    state = 'On' if env.metadata_cache_enabled else 'Off (set METADATA_CACHE_ENABLE=true to enable)'
    token_json = json.dumps(token).replace('<', '\\u003c')
    entries_json = json.dumps(entries).replace('<', '\\u003c')
    body = (
        _TEMPLATE.replace('__STATE__', state)
        .replace('__TOKEN__', token_json)
        .replace('__ENTRIES_JSON__', entries_json)
        .replace('__TOTAL__', json.dumps(total))
        .replace('__STUDIOS__', json.dumps(studios).replace('<', '\\u003c'))
        .replace('__FACETS__', json.dumps(facets).replace('<', '\\u003c'))
        .replace('__DUP_KEYS__', json.dumps(dup_keys).replace('<', '\u003c'))
    )
    return HTMLResponse(body)


@router.get('/edit', response_class=HTMLResponse)
async def edit_page(request: Request, key: str = '') -> HTMLResponse:
    loaded = await run_in('store', metadata_cache.load_for_edit, key) if '/' in key else None
    if loaded is None:
        return HTMLResponse('<p style="font-family:system-ui;color:#e2e8f0;background:#0f1117">No snapshot for that key.</p>', status_code=404)
    md = (loaded.get('MediaContainer') or {}).get('Metadata') or [{}]
    subtitle = f'<code>{html.escape(key)}</code>'
    body = (
        _EDIT_TEMPLATE.replace('__SUBTITLE__', subtitle)
        .replace('__TOKEN__', _json_attr(request.query_params.get('token', '')))
        .replace('__KEY__', _json_attr(key))
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
    provider: str = '',
    dups: int = Query(0, ge=0, le=1),
    sort: str = 'updated_at',
    direction: str = Query('desc', alias='dir'),
    limit: int = Query(500, ge=0, le=1000),
    offset: int = Query(0, ge=0),
) -> JSONResponse:
    sort = sort if sort in _SORT_KEYS else 'updated_at'
    direction = direction if direction in ('asc', 'desc') else 'desc'
    entries, total = await run_in(
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
            provider=provider,
            dups_only=bool(dups),
            sort=sort,
            direction=direction,
            limit=limit if limit > 0 else -1,
            offset=offset,
        ),
    )
    return JSONResponse(
        {
            'entries': entries,
            'dup_keys': await run_in('store', metadata_cache.duplicate_entries),
            'total': total,
            'studios': await run_in('store', metadata_cache.studios),
            'facets': await run_in('store', metadata_cache.facets),
        }
    )


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
    purged = 0
    for key in keys:
        if await run_in('store', metadata_cache.purge, key):
            purged += 1
    return JSONResponse({'ok': True, 'purged': purged})


@router.post('/purge-duplicates')
async def purge_duplicates() -> JSONResponse:
    return JSONResponse({'ok': True, 'purged': await run_in('store', metadata_cache.purge_duplicates)})
