from __future__ import annotations

import importlib.util
from typing import Any

from app.utils.http.bypass_types import BypassRequest, BypassResponse
from app.utils.images.ext import is_image_content_type
from app.utils.logging.logger import logger

_IMPERSONATE = 'chrome120'


class _ImpersonateBackend:
    """Presents a Chrome TLS/HTTP2 fingerprint via curl_cffi so Cloudflare lets the request
    through without a JS challenge; unlike FlareSolverr it forwards our custom headers."""

    name = 'Impersonate'

    def is_available(self) -> bool:
        return importlib.util.find_spec('curl_cffi') is not None

    async def request(self, req: BypassRequest) -> BypassResponse | None:
        try:
            from curl_cffi.requests import AsyncSession
        except ImportError:
            logger.debug('bypass:Impersonate', 'curl_cffi not installed; skipping')
            return None

        timeout = (req.timeout_ms or 30_000) / 1000
        kwargs: dict[str, Any] = {
            'headers': req.headers or None,
            'cookies': req.cookies or None,
            'impersonate': _IMPERSONATE,
            'timeout': timeout,
            'allow_redirects': True,
        }
        try:
            async with AsyncSession() as session:
                if req.method == 'POST':
                    r = await session.post(req.url, data=req.body, **kwargs)
                else:
                    r = await session.get(req.url, **kwargs)
        except Exception as err:  # noqa: BLE001 - any curl_cffi failure → skip backend
            logger.warn('bypass:Impersonate', f'{req.url} failed: {err}')
            return None

        try:
            cookies = dict(r.cookies)
        except (TypeError, ValueError):
            cookies = {}
        return BypassResponse(status=r.status_code, body=r.text, headers=dict(r.headers), cookies=cookies, final_url=str(r.url))


impersonate_backend = _ImpersonateBackend()


async def impersonate_get_bytes(url: str, headers: dict[str, str] | None = None, timeout_ms: int = 30_000) -> tuple[bytes, str] | None:
    """Fetch binary content (e.g. a Cloudflare-gated image) via curl_cffi TLS impersonation; returns
    (bytes, content_type) on a 2xx image response, else None. BypassResponse is text-only, hence this."""
    if not impersonate_backend.is_available():
        return None
    try:
        from curl_cffi.requests import AsyncSession
    except ImportError:
        return None
    try:
        async with AsyncSession() as session:
            r = await session.get(url, headers=headers or None, impersonate=_IMPERSONATE, timeout=timeout_ms / 1000, allow_redirects=True)
    except Exception as err:  # noqa: BLE001 - any curl_cffi failure → no bytes
        logger.warn('bypass:Impersonate', f'binary GET {url} failed: {err}')
        return None
    if not 200 <= r.status_code < 300:
        logger.debug('bypass:Impersonate', f'binary GET {url} -> {r.status_code}')
        return None
    content_type = r.headers.get('content-type', '')
    if not is_image_content_type(content_type):
        logger.debug('bypass:Impersonate', f'binary GET {url} non-image content-type {content_type!r}')
        return None
    return r.content, content_type
