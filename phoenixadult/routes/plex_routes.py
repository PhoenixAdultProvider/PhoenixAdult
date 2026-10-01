from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import httpx2
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from phoenixadult.config.env import TRUTHY
from phoenixadult.routes import read_json_body
from phoenixadult.services import plex_account, plex_connections, plex_import, plex_jobs, plex_reconcile
from phoenixadult.services.plex_connections import Connection
from phoenixadult.utils.auth.user_auth import admin_auth_guard, csrf_guard, resolve_user, user_auth_guard
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.logging.logger import logger

router = APIRouter(dependencies=[Depends(user_auth_guard), Depends(csrf_guard)])
_admin = [Depends(admin_auth_guard)]


def _truthy(value: str | None) -> bool:
    return (value or '').strip().lower() in TRUTHY


def _limit(request: Request) -> tuple[int | None, JSONResponse | None]:
    raw = request.query_params.get('limit')
    if not raw:
        return None, None
    try:
        value = int(raw)
    except ValueError:
        return None, JSONResponse({'error': 'limit must be an integer'}, status_code=400)
    if value < 0:
        return None, JSONResponse({'error': 'limit must be an integer'}, status_code=400)
    return value, None


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
    wanted = [str(c) for c in body['allowedClients']] if isinstance(body.get('allowedClients'), list) else None
    if wanted is not None and (taken := await run_in('store', plex_connections.claimed_by_other_users, connection_id, wanted)):
        return JSONResponse({'error': f'Already registered by another user: {", ".join(taken)}'}, status_code=409)
    fields: dict[str, Any] = {k: v for k, v in body.items() if k != 'allowedClients'}
    if fields:
        await run_in('store', plex_connections.update_fields, connection_id, fields)
    if wanted is not None:
        await run_in('store', plex_connections.set_allowed_clients, connection_id, wanted)
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


async def _advertised(url: str, token: str, client_id: str) -> bool:
    host = (urlsplit(url).hostname or '').strip('[]').lower()
    if not host or not token:
        return False
    try:
        return host in await plex_account.advertised_hosts(token, client_id)
    except (httpx2.HTTPError, ValueError) as err:
        logger.warn('plex-auth', f'could not list advertised servers: {err}')
        return False


@router.post('/connections/{connection_id}/verify', dependencies=_admin)
async def verify(connection_id: int, request: Request) -> JSONResponse:
    connection = await _owned(request, connection_id)
    if connection is None:
        return JSONResponse({'error': 'No such connection'}, status_code=404)
    body = await read_json_body(request)
    override = str(body.get('url') or '').strip()
    url = override or connection.server_url
    if not url:
        return JSONResponse({'error': 'This connection has no server URL'}, status_code=400)
    token = await run_in('store', plex_connections.token_for, connection_id) or ''
    if override and override.rstrip('/') != connection.server_url.rstrip('/') and not await _advertised(override, token, connection.client_id):
        return JSONResponse({'error': 'That address is not one your Plex account advertises for this server'}, status_code=400)
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


@router.get('/connections/{connection_id}/jobs')
async def jobs(connection_id: int, request: Request) -> JSONResponse:
    if await _owned(request, connection_id) is None:
        return JSONResponse({'error': 'No such connection'}, status_code=404)
    return JSONResponse({'jobs': plex_jobs.status_for(connection_id)})


@router.post('/connections/{connection_id}/reconcile')
async def reconcile(connection_id: int, request: Request) -> JSONResponse:
    resolved = await _with_token(request, connection_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    connection, token = resolved

    limit, error = _limit(request)
    if error is not None:
        return error

    def _csv(name: str) -> set[str] | None:
        raw = (request.query_params.get(name) or '').strip()
        return {v.strip() for v in raw.split(',') if v.strip()} or None if raw else None

    apply = _truthy(request.query_params.get('apply'))
    fields, sites = _csv('fields'), _csv('sites')

    def _factory() -> Any:
        return plex_reconcile.reconcile(
            connection,
            token,
            apply=apply,
            limit=limit,
            fields=fields,
            sites=sites,
            on_progress=lambda total, done: plex_jobs.set_progress(connection_id, 'reconcile', total=total, done=done, phase='inspecting'),
        )

    if not plex_jobs.launch(connection_id, 'reconcile', _factory):
        return JSONResponse({'error': 'A reconcile is already running for this connection'}, status_code=409)
    return JSONResponse({'started': True, 'kind': 'reconcile'})


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


@router.post('/connections/{connection_id}/import', dependencies=_admin)
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

    apply = _truthy(request.query_params.get('apply'))
    overwrite = _truthy(request.query_params.get('overwrite'))

    def _factory() -> Any:
        return plex_import.import_library(connection, token, section, apply=apply, limit=limit, overwrite=overwrite)

    if not plex_jobs.launch(connection_id, 'import', _factory):
        return JSONResponse({'error': 'An import is already running for this connection'}, status_code=409)
    return JSONResponse({'started': True, 'kind': 'import'})


@router.post('/connections/{connection_id}/import-item', dependencies=_admin)
async def import_item(connection_id: int, request: Request) -> JSONResponse:
    resolved = await _with_token(request, connection_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    connection, token = resolved

    rating_key = (request.query_params.get('ratingKey') or '').strip()
    if not rating_key:
        return JSONResponse({'error': 'ratingKey is required'}, status_code=400)
    overwrite = _truthy(request.query_params.get('overwrite'))
    try:
        item = await plex_import.import_item(connection, token, rating_key, overwrite=overwrite)
    except httpx2.HTTPError as err:
        logger.warn('plex-import', f'single import failed for {rating_key}: {err}')
        return JSONResponse({'error': 'Could not fetch the item from Plex'}, status_code=502)
    return JSONResponse({'item': item.as_dict()})


@router.post('/connections/{connection_id}/collection-logos')
async def collection_logos(connection_id: int, request: Request) -> JSONResponse:
    resolved = await _with_token(request, connection_id)
    if isinstance(resolved, JSONResponse):
        return resolved
    connection, token = resolved
    limit, error = _limit(request)
    if error is not None:
        return error

    apply = _truthy(request.query_params.get('apply'))

    def _factory() -> Any:
        return plex_reconcile.push_collection_logos(connection, token, apply=apply, limit=limit)

    if not plex_jobs.launch(connection_id, 'collection-logos', _factory):
        return JSONResponse({'error': 'A collection-logos run is already active for this connection'}, status_code=409)
    return JSONResponse({'started': True, 'kind': 'collection-logos'})
