from __future__ import annotations

from fastapi import HTTPException, Request

from phoenixadult.services.plex_connections import allowed_client_union
from phoenixadult.utils.auth.user_auth import _is_loopback, resolve_user
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.logging.logger import logger


def _reason(client_id: str, allowed_count: int) -> str:
    if not client_id:
        return (
            f'it sent no X-Plex-Client-Identifier header, so none of the {allowed_count} registered client(s) can ever match it. '
            'Clear the list under Config > Plex > Allowed Plex Clients to accept requests like this one'
        )
    return (
        f'client "{client_id}" is not one of the {allowed_count} registered. '
        'Copy it from Config > Clients into Config > Plex > Allowed Plex Clients, or clear that list to turn this check off'
    )


async def plex_client_guard(request: Request) -> None:
    where = f'{request.method} {request.url.path}'
    origin = request.client.host if request.client else None
    allowed = await run_in('store', allowed_client_union)
    if not allowed:
        logger.debug('auth', f'allowed {where}: no Plex clients are registered, so this check is off')
        return
    client_id = (request.headers.get('x-plex-client-identifier') or '').strip()
    if client_id in allowed:
        logger.debug('auth', f'allowed {where}: client "{client_id}" is registered')
        return
    if _is_loopback(origin):
        logger.debug('auth', f'allowed {where}: the request came from loopback')
        return
    if await resolve_user(request) is not None:
        logger.debug('auth', f'allowed {where}: the request carried a valid session or API key')
        return
    logger.warn('auth', f'rejected {where} from {origin or "an unknown address"} - {_reason(client_id, len(allowed))}.')
    raise HTTPException(status_code=403, detail='Client not allowed')
