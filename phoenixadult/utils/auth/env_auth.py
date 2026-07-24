from __future__ import annotations

import hmac

from fastapi import HTTPException, Request

from phoenixadult.config.env import env


def _token_matches(presented: str | None, expected: str) -> bool:
    if not presented:
        return False
    return hmac.compare_digest(presented, expected)


def _is_loopback(ip: str | None) -> bool:
    if not ip:
        return False
    h = ip.removeprefix('::ffff:')
    return h in ('127.0.0.1', '::1') or h.startswith('127.')


def _presented_token(request: Request) -> str | None:
    auth = request.headers.get('authorization')
    if auth and auth.startswith('Bearer '):
        return auth[7:].strip()
    header = request.headers.get('x-admin-token')
    if header:
        return header.strip()
    token = request.query_params.get('token')
    if token:
        return token.strip()
    return None


_SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS'}


async def csrf_guard(request: Request) -> None:
    """Fetch-metadata check: browsers send Sec-Fetch-Site on every request, so a
    drive-by cross-site POST is rejected; non-browser clients (no header) pass."""
    if request.method in _SAFE_METHODS:
        return
    sec_fetch_site = request.headers.get('sec-fetch-site')
    if sec_fetch_site and sec_fetch_site not in ('same-origin', 'none'):
        raise HTTPException(status_code=403, detail='Cross-site request rejected')


async def env_auth_guard(request: Request) -> None:
    """No ADMIN_TOKEN configured means auth is disabled entirely (admin surfaces open to all)."""
    token = env.admin_token
    if token is None:
        return
    client_ip = request.client.host if request.client else None
    if _is_loopback(client_ip):
        return
    if _token_matches(_presented_token(request), token):
        return
    raise HTTPException(status_code=401, detail='Unauthorized')
