from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from phoenixadult.config.env import env
from phoenixadult.routes import read_json_body
from phoenixadult.utils import cache as metadata_cache
from phoenixadult.utils.auth.env_auth import csrf_guard, env_auth_guard
from phoenixadult.utils.helpers.helpers import load_data

router = APIRouter(dependencies=[Depends(env_auth_guard), Depends(csrf_guard)])

_TEMPLATE: str = load_data(__file__, 'metadata_cache', kind='html')

_SORT_KEYS = ('title', 'studio', 'release_date', 'updated_at')


@router.get('', response_class=HTMLResponse)
@router.get('/', response_class=HTMLResponse)
async def page(request: Request) -> HTMLResponse:
    entries, total = await asyncio.to_thread(metadata_cache.entries_page)
    dup_keys = await asyncio.to_thread(metadata_cache.duplicate_entries)
    studios = await asyncio.to_thread(metadata_cache.studios)
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
        .replace('__DUP_KEYS__', json.dumps(dup_keys).replace('<', '\u003c'))
    )
    return HTMLResponse(body)


@router.get('/state')
async def state() -> JSONResponse:
    return JSONResponse({'token': await asyncio.to_thread(metadata_cache.change_token)})


@router.get('/entries')
async def entries_json(
    studio: str = '',
    query: str = Query('', alias='q'),
    sort: str = 'updated_at',
    direction: str = Query('desc', alias='dir'),
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> JSONResponse:
    sort = sort if sort in _SORT_KEYS else 'updated_at'
    direction = direction if direction in ('asc', 'desc') else 'desc'
    entries, total = await asyncio.to_thread(
        lambda: metadata_cache.entries_page(studio=studio, query=query, sort=sort, direction=direction, limit=limit, offset=offset)
    )
    return JSONResponse(
        {
            'entries': entries,
            'dup_keys': await asyncio.to_thread(metadata_cache.duplicate_entries),
            'total': total,
            'studios': await asyncio.to_thread(metadata_cache.studios),
        }
    )


@router.post('/purge')
async def purge(request: Request) -> JSONResponse:
    data = await read_json_body(request)
    key = str(data.get('key', ''))
    if '/' not in key:
        return JSONResponse({'ok': False, 'error': 'bad key'}, status_code=400)
    ok = await asyncio.to_thread(metadata_cache.purge, key)
    return JSONResponse({'ok': ok})


@router.post('/purge-bulk')
async def purge_bulk(request: Request) -> JSONResponse:
    data = await read_json_body(request)
    keys = data.get('keys')
    if not isinstance(keys, list) or not keys or not all(isinstance(k, str) and '/' in k for k in keys):
        return JSONResponse({'ok': False, 'error': 'bad keys'}, status_code=400)
    purged = 0
    for key in keys:
        if await asyncio.to_thread(metadata_cache.purge, key):
            purged += 1
    return JSONResponse({'ok': True, 'purged': purged})


@router.post('/purge-duplicates')
async def purge_duplicates() -> JSONResponse:
    return JSONResponse({'ok': True, 'purged': await asyncio.to_thread(metadata_cache.purge_duplicates)})
