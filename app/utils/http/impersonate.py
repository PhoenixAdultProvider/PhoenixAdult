from __future__ import annotations

import importlib.util
from typing import Any

from app.utils.http.bypass_types import BypassRequest, BypassResponse
from app.utils.logging.logger import logger

# Chrome TLS/HTTP2 fingerprint to present. Cloudflare fingerprint-blocks the default
# Python TLS handshake; curl_cffi mimics a real browser so the request is let through
# WITHOUT a JS challenge — and (unlike FlareSolverr) it forwards our custom headers.
_IMPERSONATE = 'chrome120'


class _ImpersonateBackend:
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
