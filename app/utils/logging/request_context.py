from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.utils.logging.context import request_id_scope
from app.utils.logging.logger import logger

Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def _header(headers: dict[bytes, bytes], key: bytes) -> str | None:
    value = headers.get(key)
    return value.decode('latin-1') if value is not None else None


class RequestContextMiddleware:
    """Pure-ASGI middleware: one request id per HTTP request.

    A pure-ASGI (not BaseHTTPMiddleware) middleware runs the app in the SAME task,
    so the contextvar id set here is visible to the endpoint and every nested
    agent/scraper log. The access line is emitted here, in-scope, so it carries the
    same id (uvicorn's own access log is disabled in configure_uvicorn_logging).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        status = {'code': 0}

        async def send_wrapper(message: Message) -> None:
            if message['type'] == 'http.response.start':
                status['code'] = message['status']
            await send(message)

        with request_id_scope():
            try:
                await self.app(scope, receive, send_wrapper)
            finally:
                headers = dict(scope.get('headers') or [])
                logger.http(
                    f'{scope["method"]} {scope["path"]} -> {status["code"]}',
                    language=_header(headers, b'x-plex-language'),
                    country=_header(headers, b'x-plex-country'),
                )
