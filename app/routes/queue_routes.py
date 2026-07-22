from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.routes import read_json_body
from app.services import scrape_queue
from app.utils.auth.env_auth import csrf_guard, env_auth_guard
from app.utils.helpers.helpers import load_data
from app.utils.http.rate_limit_helper import pacer_states

router = APIRouter(dependencies=[Depends(env_auth_guard), Depends(csrf_guard)])

_TEMPLATE: str = load_data(__file__, 'queue_ui', kind='html')


def _state() -> dict[str, object]:
    return {'pacers': pacer_states(), **scrape_queue.snapshot()}


@router.get('', response_class=HTMLResponse)
@router.get('/', response_class=HTMLResponse)
async def page(request: Request) -> HTMLResponse:
    return HTMLResponse(_TEMPLATE.replace('__STATE_JSON__', json.dumps(_state())))


@router.get('/api/state')
async def state() -> JSONResponse:
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
