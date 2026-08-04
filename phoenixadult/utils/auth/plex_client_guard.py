from __future__ import annotations

from fastapi import HTTPException, Request

from phoenixadult.config.env import env
from phoenixadult.utils.auth.user_auth import _is_loopback, resolve_user
from phoenixadult.utils.logging.logger import logger


async def plex_client_guard(request: Request) -> None:
    allowed = env.plex_client_allowlist
    if not allowed:
        return
    client_id = (request.headers.get('x-plex-client-identifier') or '').strip()
    if client_id in allowed:
        return
    if _is_loopback(request.client.host if request.client else None):
        return
    if await resolve_user(request) is not None:
        return
    logger.warn('auth', f'rejected provider request with unapproved X-Plex-Client-Identifier ({request.method} {request.url.path})')
    raise HTTPException(status_code=403, detail='Client not allowed')
