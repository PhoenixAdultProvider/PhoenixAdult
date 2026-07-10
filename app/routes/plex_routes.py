from __future__ import annotations

import httpx2
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.services import plex_reconcile
from app.utils.auth.env_auth import csrf_guard, env_auth_guard
from app.utils.logging.logger import logger

router = APIRouter(dependencies=[Depends(env_auth_guard), Depends(csrf_guard)])


def _truthy(value: str | None) -> bool:
    return (value or '').strip().lower() in ('1', 'true', 'yes', 'on')


@router.get('/status')
async def status() -> JSONResponse:
    return JSONResponse({'enabled': plex_reconcile.enabled()})


@router.post('/reconcile')
async def reconcile(request: Request) -> JSONResponse:
    if not plex_reconcile.enabled():
        return JSONResponse({'error': 'Set PLEX_URL and PLEX_TOKEN to enable reconciliation'}, status_code=409)

    apply = _truthy(request.query_params.get('apply'))
    raw_limit = request.query_params.get('limit')
    try:
        limit = int(raw_limit) if raw_limit else None
    except ValueError:
        return JSONResponse({'error': 'limit must be an integer'}, status_code=400)

    try:
        report = await plex_reconcile.reconcile(apply=apply, limit=limit)
    except httpx2.HTTPError as err:
        logger.warn('plex-reconcile', f'Plex request failed: {err}')
        return JSONResponse({'error': 'Plex request failed'}, status_code=502)
    return JSONResponse(report.as_dict())
