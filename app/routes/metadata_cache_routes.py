from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.config.env import env
from app.routes import read_json_body
from app.utils import cache as metadata_cache
from app.utils.auth.env_auth import csrf_guard, env_auth_guard
from app.utils.helpers.helpers import load_data

router = APIRouter(dependencies=[Depends(env_auth_guard), Depends(csrf_guard)])

_TEMPLATE: str = load_data(__file__, 'metadata_cache', kind='html')


@router.get('', response_class=HTMLResponse)
@router.get('/', response_class=HTMLResponse)
async def page(request: Request) -> HTMLResponse:
    entries = await asyncio.to_thread(metadata_cache.entries)
    dup_keys = await asyncio.to_thread(metadata_cache.duplicate_entries)
    token = request.query_params.get('token', '')
    state = 'On' if env.metadata_cache_enabled else 'Off (set METADATA_CACHE_ENABLE=true to enable)'
    token_json = json.dumps(token).replace('<', '\\u003c')
    entries_json = json.dumps(entries).replace('<', '\\u003c')
    body = (
        _TEMPLATE.replace('__STATE__', state)
        .replace('__TOKEN__', token_json)
        .replace('__ENTRIES_JSON__', entries_json)
        .replace('__DUP_KEYS__', json.dumps(dup_keys).replace('<', '\u003c'))
    )
    return HTMLResponse(body)


@router.get('/state')
async def state() -> JSONResponse:
    return JSONResponse({'token': await asyncio.to_thread(metadata_cache.change_token)})


@router.get('/entries')
async def entries_json() -> JSONResponse:
    return JSONResponse(
        {
            'entries': await asyncio.to_thread(metadata_cache.entries),
            'dup_keys': await asyncio.to_thread(metadata_cache.duplicate_entries),
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
