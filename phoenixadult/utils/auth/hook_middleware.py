from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from phoenixadult.utils.auth import rate_limit, user_store
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.logging.logger import logger

Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

HOOK_PREFIX = '/api/hook/'


def _provider_mounts() -> tuple[str, ...]:
    from phoenixadult.registry import get_all_providers
    from phoenixadult.utils.plex.media_type import provider_mount_path

    return tuple(provider_mount_path(p) for p in get_all_providers())


async def _respond(send: Send, status: int, body: dict[str, Any], headers: list[tuple[bytes, bytes]] | None = None) -> None:
    payload = json.dumps(body).encode()
    base = [(b'content-type', b'application/json'), (b'content-length', str(len(payload)).encode())]
    await send({'type': 'http.response.start', 'status': status, 'headers': base + (headers or [])})
    await send({'type': 'http.response.body', 'body': payload})


class HookPathMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.mounts: tuple[str, ...] = ()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get('type') != 'http' or not scope.get('path', '').startswith(HOOK_PREFIX):
            await self.app(scope, receive, send)
            return

        origin = (scope.get('client') or ('unknown',))[0]
        wait = rate_limit.retry_after('hook', origin)
        if wait > 0:
            await _respond(send, 429, {'error': 'Too many attempts'}, [(b'retry-after', str(int(wait) + 1).encode())])
            return

        token, _, rest = scope['path'][len(HOOK_PREFIX) :].partition('/')
        rest = f'/{rest}'
        user = await run_in('auth', user_store.user_for_api_key, token) if token else None
        if user is None:
            rate_limit.record_failure('hook', origin)
            logger.warn('auth', f'refused {scope.get("method", "GET")} {scope["path"]} from {origin} - the hook token matches no user API key.')
            await _respond(send, 404, {'error': 'Not found'})
            return
        rate_limit.record_success('hook', origin)

        if not self.mounts:
            self.mounts = _provider_mounts()
        if not any(rest == mount or rest.startswith(f'{mount}/') for mount in self.mounts):
            logger.warn('auth', f'refused {scope.get("method", "GET")} {scope["path"]} from {origin} - hook URLs serve only the provider mount.')
            await _respond(send, 404, {'error': 'Not found'})
            return

        scope['path'] = rest
        scope['raw_path'] = rest.encode()
        scope.setdefault('state', {})['hook_user'] = user
        await self.app(scope, receive, send)
