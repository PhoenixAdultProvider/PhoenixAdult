from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.config.env import env
from app.routes import read_json_body
from app.utils import cache as metadata_cache
from app.utils.auth.env_auth import csrf_guard, env_auth_guard

router = APIRouter(dependencies=[Depends(env_auth_guard), Depends(csrf_guard)])

_TEMPLATE = (Path(__file__).parent / 'html' / 'metadata_cache.html').read_text(encoding='utf-8')


@router.get('', response_class=HTMLResponse)
@router.get('/', response_class=HTMLResponse)
async def page(request: Request) -> HTMLResponse:
    entries = await asyncio.to_thread(metadata_cache.entries)
    dup_keys = await asyncio.to_thread(metadata_cache.duplicate_entries)
    token = request.query_params.get('token', '')
    state = 'On' if env.metadata_cache_enabled else 'Off (set METADATA_CACHE_ENABLE=true to enable)'
    # Escape `<` so scraped titles / a crafted ?token= can't break out of the <script> block.
    token_json = json.dumps(token).replace('<', '\\u003c')
    entries_json = json.dumps(entries).replace('<', '\\u003c')
    body = (
        _TEMPLATE.replace('__STATE__', state)
        .replace('__TOKEN__', token_json)
        .replace('__ENTRIES_JSON__', entries_json)
        .replace('__DUP_KEYS__', json.dumps(dup_keys).replace('<', '\u003c'))
    )
    return HTMLResponse(body)


@router.post('/purge')
async def purge(request: Request) -> JSONResponse:
    data = await read_json_body(request)
    key = str(data.get('key', ''))
    if '/' not in key:
        return JSONResponse({'ok': False, 'error': 'bad key'}, status_code=400)
    ok = await asyncio.to_thread(metadata_cache.purge, key)
    return JSONResponse({'ok': ok})


@router.post('/purge-duplicates')
async def purge_duplicates() -> JSONResponse:
    # Recomputed server-side; the client never supplies paths.
    return JSONResponse({'ok': True, 'purged': await asyncio.to_thread(metadata_cache.purge_duplicates)})
