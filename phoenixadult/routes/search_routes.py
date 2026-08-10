from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from phoenixadult.routes import nav_username, read_json_body, render_page
from phoenixadult.utils.auth.user_auth import admin_auth_guard, csrf_guard, user_auth_guard
from phoenixadult.utils.cache import search_store
from phoenixadult.utils.concurrency.pools import run_in

router = APIRouter(dependencies=[Depends(user_auth_guard), Depends(csrf_guard), Depends(admin_auth_guard)])


@router.get('', response_class=HTMLResponse)
@router.get('/', response_class=HTMLResponse)
async def page(request: Request) -> HTMLResponse:
    state = await run_in('store', search_store.dump)
    return HTMLResponse(render_page('searches_ui', active='searches', username=nav_username(request), state=state))


@router.get('/api/list')
async def list_state() -> JSONResponse:
    return JSONResponse(await run_in('store', search_store.dump))


@router.post('/api/purge')
async def purge(request: Request) -> JSONResponse:
    body = await read_json_body(request)
    key_hash = str(body.get('keyHash') or '')
    if not key_hash:
        return JSONResponse({'error': 'keyHash is required'}, status_code=400)
    if not await run_in('store', search_store.purge, key_hash):
        return JSONResponse({'error': 'no such stored search'}, status_code=404)
    return JSONResponse({'ok': True, **await run_in('store', search_store.dump)})


@router.post('/api/purge-site')
async def purge_site(request: Request) -> JSONResponse:
    body = await read_json_body(request)
    site = str(body.get('site') or '')
    if not site:
        return JSONResponse({'error': 'site is required'}, status_code=400)
    purged = await run_in('store', search_store.purge_site, site)
    return JSONResponse({'ok': True, 'purged': purged, **await run_in('store', search_store.dump)})


@router.post('/api/purge-all')
async def purge_all() -> JSONResponse:
    purged = await run_in('store', search_store.purge_all)
    return JSONResponse({'ok': True, 'purged': purged, **await run_in('store', search_store.dump)})


@router.post('/api/sweep')
async def sweep() -> JSONResponse:
    removed = await run_in('store', search_store.sweep_expired)
    return JSONResponse({'ok': True, 'removed': removed, **await run_in('store', search_store.dump)})


@router.post('/api/research')
async def research(request: Request) -> JSONResponse:
    from phoenixadult.routes.provider_router import match_service_for
    from phoenixadult.utils import db

    body = await read_json_body(request)
    key_hash = str(body.get('keyHash') or '')
    if not key_hash:
        return JSONResponse({'error': 'keyHash is required'}, status_code=400)

    def _take() -> dict[str, str] | None:
        row = db.connect().execute('SELECT site, title, date, scene_id, language FROM searches WHERE key_hash = ?', (key_hash,)).fetchone()
        if row is None:
            return None
        search_store.purge(key_hash)
        return {
            'search_site': str(row['site']),
            'title': str(row['title']),
            'date': str(row['date'] or ''),
            'scene_id': str(row['scene_id'] or ''),
            'language': str(row['language'] or ''),
        }

    replay = await run_in('store', _take)
    if replay is None:
        return JSONResponse({'error': 'no such stored search'}, status_code=404)
    resolved = match_service_for('phoenixadult')
    if resolved is None:
        return JSONResponse({'error': 'provider not mounted'}, status_code=500)
    provider, match_service = resolved
    match_service.requeue_search(replay, provider)
    return JSONResponse({'ok': True, **await run_in('store', search_store.dump)})
