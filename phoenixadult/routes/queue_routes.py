from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from phoenixadult.routes import nav_username, read_json_body, render_page
from phoenixadult.services import scrape_queue
from phoenixadult.utils.auth.user_auth import admin_auth_guard, csrf_guard, user_auth_guard
from phoenixadult.utils.http.rate_limit_helper import FAST_GATE, pacer_states

router = APIRouter(dependencies=[Depends(user_auth_guard), Depends(csrf_guard)])
_admin = [Depends(admin_auth_guard)]

_WATCH_TIMEOUT = 25.0


def _state() -> dict[str, object]:
    return {'pacers': pacer_states(), 'fastLane': FAST_GATE.state(), **scrape_queue.snapshot()}


@router.get('', response_class=HTMLResponse)
@router.get('/', response_class=HTMLResponse)
async def page(request: Request) -> HTMLResponse:
    return HTMLResponse(render_page('queue_ui', active='queue', username=nav_username(request), state=_state()))


@router.get('/api/state')
async def state(wait: int = 0, since: int = -1) -> JSONResponse:
    if wait:
        await scrape_queue.wait_for_change(since, _WATCH_TIMEOUT)
    return JSONResponse(_state())


@router.post('/api/flush', dependencies=_admin)
async def flush(request: Request) -> JSONResponse:
    body = await read_json_body(request)
    kind = str(body.get('kind') or '')
    if kind not in ('search', 'update'):
        return JSONResponse({'error': 'kind must be search or update'}, status_code=400)
    return JSONResponse({'ok': True, 'flushed': scrape_queue.flush(kind), **_state()})


@router.post('/api/pause', dependencies=_admin)
async def pause(request: Request) -> JSONResponse:
    body = await read_json_body(request)
    kind = str(body.get('kind') or '')
    if kind not in ('search', 'update'):
        return JSONResponse({'error': 'kind must be search or update'}, status_code=400)
    scrape_queue.pause_kind(kind)
    return JSONResponse({'ok': True, **_state()})


@router.post('/api/resume', dependencies=_admin)
async def resume(request: Request) -> JSONResponse:
    body = await read_json_body(request)
    kind = str(body.get('kind') or '')
    if kind:
        if kind not in ('search', 'update'):
            return JSONResponse({'error': 'kind must be search or update'}, status_code=400)
        scrape_queue.resume_kind(kind)
    else:
        scrape_queue.resume()
    return JSONResponse({'ok': True, **_state()})
