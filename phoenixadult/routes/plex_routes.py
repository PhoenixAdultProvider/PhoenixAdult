from __future__ import annotations

from typing import Any

import httpx2
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from phoenixadult.routes import read_json_body
from phoenixadult.services import plex_account, plex_connections, plex_import, plex_reconcile
from phoenixadult.services.plex_connections import Connection
from phoenixadult.utils.auth.user_auth import csrf_guard, resolve_user, user_auth_guard
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.logging.logger import logger

router = APIRouter(dependencies=[Depends(user_auth_guard), Depends(csrf_guard)])


def _truthy(value: str | None) -> bool:
    return (value or '').strip().lower() in ('1', 'true', 'yes', 'on')


def _limit(request: Request) -> tuple[int | None, JSONResponse | None]:
    raw = request.query_params.get('limit')
    if not raw:
        return None, None
    try:
        return int(raw), None
    except ValueError:
        return None, JSONResponse({'error': 'limit must be an integer'}, status_code=400)


async def _owned(request: Request, connection_id: int) -> Connection | None:
    user = await resolve_user(request)
    assert user is not None
    return await run_in('store', plex_connections.get_owned, user.id, connection_id)


async def _with_token(request: Request, connection_id: int) -> tuple[Connection, str] | JSONResponse:
    connection = await _owned(request, connection_id)
    if connection is None:
        return JSONResponse({'error': 'No such connection'}, status_code=404)
    token = await run_in('store', plex_connections.token_for, connection_id)
    if not connection.server_url or not token:
        return JSONResponse({'error': 'This connection needs a server URL and a token first'}, status_code=409)
    return connection, token


@router.get('/status')
async def status(request: Request) -> JSONResponse:
    user = await resolve_user(request)
    assert user is not None
    connections = await run_in('store', plex_connections.list_for_user, user.id)
    return JSONResponse({'enabled': any(c.server_url and c.has_token for c in connections), 'connections': len(connections)})


@router.get('/connections')
async def list_connections(request: Request) -> JSONResponse:
    user = await resolve_user(request)
    assert user is not None
    connections = await run_in('store', plex_connections.list_for_user, user.id)
    return JSONResponse({'connections': [c.as_dict() for c in connections]})


@router.post('/connections')
async def create_connection(request: Request) -> JSONResponse:
    user = await resolve_user(request)
    assert user is not None
    body = await read_json_body(request)
    name = str(body.get('name') or '').strip()
    if not name:
        return JSONResponse({'error': 'A connection name is required'}, status_code=400)
    try:
        connection_id = await run_in('store', plex_connections.create, user.id, name)
    except Exception:  # noqa: BLE001 - unique (user, name) collision
        return JSONResponse({'error': 'You already have a connection with that name'}, status_code=409)
    logger.info('plex-connections', f'created connection "{name}" for {user.username}')
    return JSONResponse({'id': connection_id})


@router.post('/connections/{connection_id}')
async def update_connection(connection_id: int, request: Request) -> JSONResponse:
    connection = await _owned(request, connection_id)
    if connection is None:
        return JSONResponse({'error': 'No such connection'}, status_code=404)
    body = await read_json_body(request)
    fields: dict[str, Any] = {k: v for k, v in body.items() if k != 'allowedClients'}
    if fields:
        await run_in('store', plex_connections.update_fields, connection_id, fields)
    if isinstance(body.get('allowedClients'), list):
        await run_in('store', plex_connections.set_allowed_clients, connection_id, [str(c) for c in body['allowedClients']])
    updated = await run_in('store', plex_connections.get, connection_id)
    return JSONResponse(updated.as_dict() if updated else {})


@router.post('/connections/{connection_id}/delete')
async def delete_connection(connection_id: int, request: Request) -> JSONResponse:
    connection = await _owned(request, connection_id)
    if connection is None:
        return JSONResponse({'error': 'No such connection'}, status_code=404)
    await run_in('store', plex_connections.delete, connection_id)
    logger.info('plex-connections', f'deleted connection "{connection.name}"')
    return JSONResponse({'ok': True})


@router.post('/connections/{connection_id}/token')
async def save_token(connection_id: int, request: Request) -> JSONResponse:
    connection = await _owned(request, connection_id)
    if connection is None:
        return JSONResponse({'error': 'No such connection'}, status_code=404)
    body = await read_json_body(request)
    await run_in('store', plex_connections.save_token, connection_id, str(body.get('token') or ''))
    return JSONResponse({'ok': True})


@router.post('/connections/{connection_id}/pin')
async def create_pin(connection_id: int, request: Request) -> JSONResponse:
    connection = await _owned(request, connection_id)
    if connection is None:
        return JSONResponse({'error': 'No such connection'}, status_code=404)
    client_id = plex_account.client_id_or_new(connection.client_id)
    if client_id != connection.client_id:
        await run_in('store', plex_connections.update_fields, connection_id, {'clientId': client_id})
    try:
        return JSONResponse(await plex_account.create_pin(client_id))
    except httpx2.HTTPError as err:
        logger.warn('plex-auth', f'plex.tv pin request failed: {err}')
        return JSONResponse({'error': 'Could not reach plex.tv'}, status_code=502)


@router.get('/connections/{connection_id}/pin/{pin_id}')
async def poll_pin(connection_id: int, pin_id: int, request: Request) -> JSONResponse:
    connection = await _owned(request, connection_id)
    if connection is None:
        return JSONResponse({'error': 'No such connection'}, status_code=404)
    try:
        token = await plex_account.check_pin(pin_id, connection.client_id)
    except httpx2.HTTPError as err:
        logger.warn('plex-auth', f'plex.tv pin poll failed: {err}')
        return JSONResponse({'error': 'Could not reach plex.tv'}, status_code=502)
    if not token:
        return JSONResponse({'saved': False})
    await run_in('store', plex_connections.save_token, connection_id, token)
    logger.info('plex-auth', f'stored a fetched token for connection "{connection.name}"')
    return JSONResponse({'saved': True})


@router.post('/connections/{connection_id}/servers')
async def servers(connection_id: int, request: Request) -> JSONResponse:
    connection = await _owned(request, connection_id)
    if connection is None:
        return JSONResponse({'error': 'No such connection'}, status_code=404)
    token = await run_in('store', plex_connections.token_for, connection_id)
    if not token:
        return JSONResponse({'error': 'Fetch or save a token first'}, status_code=409)
    try:
        return JSONResponse({'servers': await plex_account.list_servers(token, connection.client_id)})
    except httpx2.HTTPError as err:
        logger.warn('plex-auth', f'plex.tv resources failed: {err}')
        return JSONResponse({'error': 'Could not list servers from plex.tv'}, status_code=502)


@router.post('/connections/{connection_id}/verify')
async def verify(connection_id: int, request: Request) -> JSONResponse:
    connection = await _owned(request, connection_id)
    if connection is None:
        return JSONResponse({'error': 'No such connection'}, status_code=404)
    body = await read_json_body(request)
    url = str(body.get('url') or '') or connection.server_url
    if not url:
        return JSONResponse({'error': 'This connection has no server URL'}, status_code=400)
    token = await run_in('store', plex_connections.token_for, connection_id) or ''
    return JSONResponse(await plex_account.verify_server(url, token))


@router.get('/connections/{connection_id}/update')
async def update(connection_id: int, request: Request) -> JSONResponse:
    resolved = await _with_token(request, connection_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    connection, token = resolved
    try:
        return JSONResponse(await plex_account.update_status(connection, token, force=_truthy(request.query_params.get('force'))))
    except httpx2.HTTPError as err:
        logger.warn('plex-update', f'update check failed: {err}')
        return JSONResponse({'error': 'Update check failed'}, status_code=502)


@router.get('/connections/{connection_id}/reconcile/progress')
async def reconcile_progress(connection_id: int, request: Request) -> JSONResponse:
    if await _owned(request, connection_id) is None:
        return JSONResponse({'error': 'No such connection'}, status_code=404)
    return JSONResponse(plex_reconcile.progress(connection_id))


@router.post('/connections/{connection_id}/reconcile')
async def reconcile(connection_id: int, request: Request) -> JSONResponse:
    resolved = await _with_token(request, connection_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    connection, token = resolved
    if plex_reconcile.is_running(connection_id):
        return JSONResponse({'error': 'A reconcile is already running for this connection'}, status_code=409)

    limit, error = _limit(request)
    if error is not None:
        return error

    def _csv(name: str) -> set[str] | None:
        raw = (request.query_params.get(name) or '').strip()
        return {v.strip() for v in raw.split(',') if v.strip()} or None if raw else None

    try:
        report = await plex_reconcile.reconcile(
            connection, token, apply=_truthy(request.query_params.get('apply')), limit=limit, fields=_csv('fields'), sites=_csv('sites')
        )
    except httpx2.HTTPError as err:
        logger.warn('plex-reconcile', f'Plex request failed: {err}')
        return JSONResponse({'error': 'Plex request failed'}, status_code=502)
    return JSONResponse(report.as_dict())


@router.get('/connections/{connection_id}/libraries')
async def libraries(connection_id: int, request: Request) -> JSONResponse:
    resolved = await _with_token(request, connection_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    connection, token = resolved
    try:
        return JSONResponse({'libraries': await plex_import.libraries(connection, token)})
    except httpx2.HTTPError as err:
        logger.warn('plex-import', f'library list failed: {err}')
        return JSONResponse({'error': 'Could not list libraries from Plex'}, status_code=502)


@router.post('/connections/{connection_id}/import')
async def import_library(connection_id: int, request: Request) -> JSONResponse:
    resolved = await _with_token(request, connection_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    connection, token = resolved

    section = (request.query_params.get('section') or '').strip()
    if not section:
        return JSONResponse({'error': 'section is required'}, status_code=400)
    limit, error = _limit(request)
    if error is not None:
        return error

    try:
        report = await plex_import.import_library(
            connection,
            token,
            section,
            apply=_truthy(request.query_params.get('apply')),
            limit=limit,
            overwrite=_truthy(request.query_params.get('overwrite')),
        )
    except RuntimeError as err:
        return JSONResponse({'error': str(err)}, status_code=409)
    except httpx2.HTTPError as err:
        logger.warn('plex-import', f'Plex request failed: {err}')
        return JSONResponse({'error': 'Plex request failed'}, status_code=502)
    return JSONResponse(report.as_dict())


@router.post('/connections/{connection_id}/collection-logos')
async def collection_logos(connection_id: int, request: Request) -> JSONResponse:
    resolved = await _with_token(request, connection_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    connection, token = resolved
    limit, error = _limit(request)
    if error is not None:
        return error

    try:
        report = await plex_reconcile.push_collection_logos(connection, token, apply=_truthy(request.query_params.get('apply')), limit=limit)
    except httpx2.HTTPError as err:
        logger.warn('plex-reconcile', f'Plex request failed: {err}')
        return JSONResponse({'error': 'Plex request failed'}, status_code=502)
    return JSONResponse(report.as_dict())
