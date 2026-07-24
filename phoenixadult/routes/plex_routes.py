from __future__ import annotations

import httpx2
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from phoenixadult.config.env import env
from phoenixadult.routes import read_json_body
from phoenixadult.services import plex_account, plex_import, plex_reconcile
from phoenixadult.utils.auth.env_auth import csrf_guard, env_auth_guard
from phoenixadult.utils.logging.logger import logger

router = APIRouter(dependencies=[Depends(env_auth_guard), Depends(csrf_guard)])


def _truthy(value: str | None) -> bool:
    return (value or '').strip().lower() in ('1', 'true', 'yes', 'on')


@router.get('/status')
async def status() -> JSONResponse:
    return JSONResponse({'enabled': plex_reconcile.enabled()})


@router.post('/pin')
async def create_pin() -> JSONResponse:
    try:
        return JSONResponse(await plex_account.create_pin(plex_account.client_id_or_new()))
    except httpx2.HTTPError as err:
        logger.warn('plex-auth', f'plex.tv pin request failed: {err}')
        return JSONResponse({'error': 'Could not reach plex.tv'}, status_code=502)


@router.get('/pin/{pin_id}')
async def poll_pin(pin_id: int, request: Request) -> JSONResponse:
    client_id = request.query_params.get('client_id') or ''
    if not client_id:
        return JSONResponse({'error': 'client_id required'}, status_code=400)
    try:
        return JSONResponse({'token': await plex_account.check_pin(pin_id, client_id)})
    except httpx2.HTTPError as err:
        logger.warn('plex-auth', f'plex.tv pin poll failed: {err}')
        return JSONResponse({'error': 'Could not reach plex.tv'}, status_code=502)


@router.post('/servers')
async def servers(request: Request) -> JSONResponse:
    body = await read_json_body(request)
    token = str(body.get('token') or '') or env.plex_token or ''
    client_id = str(body.get('client_id') or '') or plex_account.client_id_or_new()
    if not token:
        return JSONResponse({'error': 'No Plex token — fetch or save one first'}, status_code=400)
    try:
        return JSONResponse({'servers': await plex_account.list_servers(token, client_id)})
    except httpx2.HTTPError as err:
        logger.warn('plex-auth', f'plex.tv resources failed: {err}')
        return JSONResponse({'error': 'Could not list servers from plex.tv'}, status_code=502)


@router.post('/verify')
async def verify(request: Request) -> JSONResponse:
    body = await read_json_body(request)
    url = str(body.get('url') or '') or env.plex_url or ''
    token = str(body.get('token') or '') or env.plex_token or ''
    if not url:
        return JSONResponse({'error': 'PLEX_URL is not set'}, status_code=400)
    return JSONResponse(await plex_account.verify_server(url, token))


@router.get('/update')
async def update(request: Request) -> JSONResponse:
    try:
        return JSONResponse(await plex_account.update_status(force=_truthy(request.query_params.get('force'))))
    except httpx2.HTTPError as err:
        logger.warn('plex-update', f'update check failed: {err}')
        return JSONResponse({'error': 'Update check failed'}, status_code=502)


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

    def _csv(name: str) -> set[str] | None:
        raw = (request.query_params.get(name) or '').strip()
        return {v.strip() for v in raw.split(',') if v.strip()} or None if raw else None

    try:
        report = await plex_reconcile.reconcile(apply=apply, limit=limit, fields=_csv('fields'), sites=_csv('sites'))
    except httpx2.HTTPError as err:
        logger.warn('plex-reconcile', f'Plex request failed: {err}')
        return JSONResponse({'error': 'Plex request failed'}, status_code=502)
    return JSONResponse(report.as_dict())


@router.get('/libraries')
async def libraries() -> JSONResponse:
    if not plex_reconcile.enabled():
        return JSONResponse({'error': 'Set PLEX_URL and PLEX_TOKEN to list libraries'}, status_code=409)
    try:
        return JSONResponse({'libraries': await plex_import.libraries()})
    except httpx2.HTTPError as err:
        logger.warn('plex-import', f'library list failed: {err}')
        return JSONResponse({'error': 'Could not list libraries from Plex'}, status_code=502)


@router.post('/import')
async def import_library(request: Request) -> JSONResponse:
    if not plex_reconcile.enabled():
        return JSONResponse({'error': 'Set PLEX_URL and PLEX_TOKEN to import'}, status_code=409)

    section = (request.query_params.get('section') or '').strip()
    if not section:
        return JSONResponse({'error': 'section is required'}, status_code=400)
    apply = _truthy(request.query_params.get('apply'))
    raw_limit = request.query_params.get('limit')
    try:
        limit = int(raw_limit) if raw_limit else None
    except ValueError:
        return JSONResponse({'error': 'limit must be an integer'}, status_code=400)

    try:
        report = await plex_import.import_library(section, apply=apply, limit=limit)
    except RuntimeError as err:
        return JSONResponse({'error': str(err)}, status_code=409)
    except httpx2.HTTPError as err:
        logger.warn('plex-import', f'Plex request failed: {err}')
        return JSONResponse({'error': 'Plex request failed'}, status_code=502)
    return JSONResponse(report.as_dict())


@router.post('/collection-logos')
async def collection_logos(request: Request) -> JSONResponse:
    if not plex_reconcile.enabled():
        return JSONResponse({'error': 'Set PLEX_URL and PLEX_TOKEN to push collection logos'}, status_code=409)

    apply = _truthy(request.query_params.get('apply'))
    raw_limit = request.query_params.get('limit')
    try:
        limit = int(raw_limit) if raw_limit else None
    except ValueError:
        return JSONResponse({'error': 'limit must be an integer'}, status_code=400)

    try:
        report = await plex_reconcile.push_collection_logos(apply=apply, limit=limit)
    except httpx2.HTTPError as err:
        logger.warn('plex-reconcile', f'Plex request failed: {err}')
        return JSONResponse({'error': 'Plex request failed'}, status_code=502)
    return JSONResponse(report.as_dict())
