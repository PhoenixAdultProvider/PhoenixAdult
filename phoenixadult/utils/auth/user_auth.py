from __future__ import annotations

import time
from contextvars import ContextVar

from fastapi import HTTPException, Request

from phoenixadult.utils.auth import user_store, user_tokens
from phoenixadult.utils.auth.passwords import hash_token
from phoenixadult.utils.auth.user_store import AuthedUser
from phoenixadult.utils.concurrency.pools import run_in

SESSION_COOKIE = 'pa_session'
_SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS'}

current_user_theme: ContextVar[dict[str, str] | None] = ContextVar('user_theme', default=None)
current_user_is_admin: ContextVar[bool] = ContextVar('user_is_admin', default=False)


def user_theme() -> dict[str, str]:
    return current_user_theme.get() or {'dark': '', 'light': ''}


def is_admin() -> bool:
    return current_user_is_admin.get()


class LoginRequired(Exception):
    pass


def _is_loopback(ip: str | None) -> bool:
    if not ip:
        return False
    h = ip.removeprefix('::ffff:')
    return h in ('127.0.0.1', '::1') or h.startswith('127.')


def presented_api_key(request: Request) -> str | None:
    auth = request.headers.get('authorization')
    if auth and auth.startswith('Bearer '):
        return auth[7:].strip() or None
    header = request.headers.get('x-api-key')
    return header.strip() if header else None


async def resolve_user(request: Request) -> AuthedUser | None:
    cached = getattr(request.state, 'user', 'unset')
    if cached != 'unset':
        return cached  # type: ignore[return-value]

    user: AuthedUser | None = None
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie:
        user = await run_in('store', user_store.session_user, hash_token(cookie), time.time())
    if user is None and (key := presented_api_key(request)):
        user = await run_in('store', user_store.user_for_api_key, key)
    request.state.user = user
    current_user_is_admin.set(bool(user and user.is_admin))
    if user is not None:
        current_user_theme.set({'dark': user.theme_dark, 'light': user.theme_light})
        token = await run_in('store', user_tokens.token_for_user, user.id)
        user_tokens.current_metadataapi_token.set(token)
    return user


async def user_auth_guard(request: Request) -> None:
    if await resolve_user(request) is None:
        raise LoginRequired


async def admin_auth_guard(request: Request) -> None:
    user = await resolve_user(request)
    if user is None:
        raise LoginRequired
    if not user.is_admin:
        raise HTTPException(status_code=403, detail='Admin access required')


async def csrf_guard(request: Request) -> None:
    if request.method in _SAFE_METHODS:
        return
    if getattr(request.state, 'user', None) is not None and request.state.user.via == 'api_key':
        return
    sec_fetch_site = request.headers.get('sec-fetch-site')
    if sec_fetch_site and sec_fetch_site not in ('same-origin', 'none'):
        raise HTTPException(status_code=403, detail='Cross-site request rejected')
    origin = request.headers.get('origin')
    if origin:
        from urllib.parse import urlsplit

        if urlsplit(origin).netloc != request.url.netloc:
            raise HTTPException(status_code=403, detail='Cross-site request rejected')
