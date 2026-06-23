from __future__ import annotations

import hmac

from fastapi import HTTPException, Request

from app.config.env import env


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
    q = request.query_params.get('token')
    if q:
        return q.strip()
    return None


async def env_auth_guard(request: Request) -> None:
    token = env.admin_token
    # No token configured → auth disabled entirely (admin surfaces open to all).
    if token is None:
        return
    client_ip = request.client.host if request.client else None
    if _is_loopback(client_ip):
        return
    if _token_matches(_presented_token(request), token):
        return
    raise HTTPException(status_code=401, detail='Unauthorized')
