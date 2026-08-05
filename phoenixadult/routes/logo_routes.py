from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from phoenixadult.registry import canonical_site_display
from phoenixadult.routes import nav_username, read_json_body, render_page
from phoenixadult.utils.auth.user_auth import admin_auth_guard, csrf_guard, user_auth_guard
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.images import logo_cache

router = APIRouter(dependencies=[Depends(user_auth_guard), Depends(csrf_guard)])
_admin = [Depends(admin_auth_guard)]


def _state() -> dict[str, object]:
    entries = logo_cache.entries()
    for e in entries:
        e['site'] = canonical_site_display(str(e['slug'])) or ''
    return {'dir': str(logo_cache.cache_dir()), 'logos': entries}


@router.get('', response_class=HTMLResponse)
@router.get('/', response_class=HTMLResponse)
async def page(request: Request) -> HTMLResponse:
    return HTMLResponse(render_page('logos_ui', active='logos', username=nav_username(request), state=await run_in('store', _state)))


@router.get('/api/list')
async def list_logos() -> JSONResponse:
    return JSONResponse(await run_in('store', _state))


@router.post('/api/purge', dependencies=_admin)
async def purge(request: Request) -> JSONResponse:
    body = await read_json_body(request)
    rel = str(body.get('rel') or '')
    if not rel:
        return JSONResponse({'error': 'rel required'}, status_code=400)
    if not await run_in('fs', logo_cache.purge, rel):
        return JSONResponse({'error': 'not found'}, status_code=404)
    return JSONResponse({'ok': True})


@router.post('/api/purge-all', dependencies=_admin)
async def purge_all() -> JSONResponse:
    return JSONResponse({'ok': True, 'purged': await run_in('fs', logo_cache.purge_all)})


@router.post('/api/rescan', dependencies=_admin)
async def rescan() -> JSONResponse:
    return JSONResponse({'ok': True, 'count': await run_in('fs', logo_cache.rescan)})
