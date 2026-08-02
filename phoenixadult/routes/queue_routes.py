from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from phoenixadult.routes import read_json_body, render_nav
from phoenixadult.services import scrape_queue
from phoenixadult.utils.auth.env_auth import csrf_guard, env_auth_guard
from phoenixadult.utils.helpers.helpers import load_data
from phoenixadult.utils.http.rate_limit_helper import FAST_GATE, pacer_states

router = APIRouter(dependencies=[Depends(env_auth_guard), Depends(csrf_guard)])

_TEMPLATE: str = load_data(__file__, 'queue_ui', kind='html')
_WATCH_TIMEOUT = 25.0


def _state() -> dict[str, object]:
    return {'pacers': pacer_states(), 'fastLane': FAST_GATE.state(), **scrape_queue.snapshot()}


@router.get('', response_class=HTMLResponse)
@router.get('/', response_class=HTMLResponse)
async def page(request: Request) -> HTMLResponse:
    body = _TEMPLATE.replace('__NAV__', render_nav('queue'))
    return HTMLResponse(body.replace('__STATE_JSON__', json.dumps(_state())))


@router.get('/api/state')
async def state(wait: int = 0, since: int = -1) -> JSONResponse:
    if wait:
        await scrape_queue.wait_for_change(since, _WATCH_TIMEOUT)
    return JSONResponse(_state())


@router.post('/api/flush')
async def flush(request: Request) -> JSONResponse:
    body = await read_json_body(request)
    kind = str(body.get('kind') or '')
    if kind not in ('search', 'update'):
        return JSONResponse({'error': 'kind must be search or update'}, status_code=400)
    return JSONResponse({'ok': True, 'flushed': scrape_queue.flush(kind), **_state()})


@router.post('/api/resume')
async def resume() -> JSONResponse:
    scrape_queue.resume()
    return JSONResponse({'ok': True, **_state()})
