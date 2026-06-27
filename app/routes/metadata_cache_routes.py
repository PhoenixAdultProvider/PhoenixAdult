from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.config.env import env
from app.routes.env_auth import env_auth_guard
from app.utils import cache as metadata_cache

router = APIRouter(dependencies=[Depends(env_auth_guard)])

_TEMPLATE = (Path(__file__).parent / 'html' / 'metadata_cache.html').read_text(encoding='utf-8')


@router.get('', response_class=HTMLResponse)
@router.get('/', response_class=HTMLResponse)
async def page(request: Request) -> HTMLResponse:
    entries = metadata_cache.entries()
    token = request.query_params.get('token', '')
    state = 'On' if env.metadata_cache_enabled else 'Off (set METADATA_CACHE_ENABLE=true to enable)'
    body = _TEMPLATE.replace('__STATE__', state).replace('__TOKEN__', json.dumps(token)).replace('__ENTRIES_JSON__', json.dumps(entries))
    return HTMLResponse(body)


@router.post('/purge')
async def purge(request: Request) -> JSONResponse:
    try:
        data = await request.json()
    except (ValueError, TypeError):
        data = {}
    key = str(data.get('key', '')) if isinstance(data, dict) else ''
    if '/' not in key:
        return JSONResponse({'ok': False, 'error': 'bad key'}, status_code=400)
    ok = metadata_cache.purge(key)
    return JSONResponse({'ok': ok})
