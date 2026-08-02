from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from phoenixadult.registry import canonical_site_display
from phoenixadult.routes import read_json_body, render_nav
from phoenixadult.utils.auth.env_auth import csrf_guard, env_auth_guard
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.helpers.helpers import load_data
from phoenixadult.utils.images import logo_cache

router = APIRouter(dependencies=[Depends(env_auth_guard), Depends(csrf_guard)])

_TEMPLATE: str = load_data(__file__, 'logos_ui', kind='html')


def _state() -> dict[str, object]:
    entries = logo_cache.entries()
    for e in entries:
        e['site'] = canonical_site_display(str(e['slug'])) or ''
    return {'dir': str(logo_cache.cache_dir()), 'logos': entries}


@router.get('', response_class=HTMLResponse)
@router.get('/', response_class=HTMLResponse)
async def page(request: Request) -> HTMLResponse:
    body = _TEMPLATE.replace('__NAV__', render_nav('logos'))
    return HTMLResponse(body.replace('__STATE_JSON__', json.dumps(await run_in('store', _state))))


@router.get('/api/list')
async def list_logos() -> JSONResponse:
    return JSONResponse(await run_in('store', _state))


@router.post('/api/purge')
async def purge(request: Request) -> JSONResponse:
    body = await read_json_body(request)
    rel = str(body.get('rel') or '')
    if not rel:
        return JSONResponse({'error': 'rel required'}, status_code=400)
    if not await run_in('fs', logo_cache.purge, rel):
        return JSONResponse({'error': 'not found'}, status_code=404)
    return JSONResponse({'ok': True})


@router.post('/api/purge-all')
async def purge_all() -> JSONResponse:
    return JSONResponse({'ok': True, 'purged': await run_in('fs', logo_cache.purge_all)})


@router.post('/api/rescan')
async def rescan() -> JSONResponse:
    return JSONResponse({'ok': True, 'count': await run_in('fs', logo_cache.rescan)})
