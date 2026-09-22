from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_HEADERS = (
    (b'x-frame-options', b'DENY'),
    (b'content-security-policy', b"frame-ancestors 'none'"),
    (b'x-content-type-options', b'nosniff'),
)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message['type'] == 'http.response.start':
                headers = list(message.get('headers', []))
                present = {name.lower() for name, _ in headers}
                message['headers'] = headers + [header for header in _HEADERS if header[0] not in present]
            await send(message)

        await self.app(scope, receive, send_with_headers)
