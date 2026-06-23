from __future__ import annotations

import httpx2

from app.config.env import env
from app.utils.logging.logger import logger

DEFAULT_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'


def _proxy_url() -> str | None:
    raw = env.https_proxy
    return raw.strip() if raw and raw.strip() else None


async def _log_request(request: httpx2.Request) -> None:
    logger.info(f'Requesting {request.method.upper()} "{request.url}"')


def make_http(extra_headers: dict[str, str] | None = None) -> httpx2.AsyncClient:
    headers = {'User-Agent': DEFAULT_UA, **(extra_headers or {})}
    proxy = _proxy_url()
    return httpx2.AsyncClient(
        timeout=15.0,
        headers=headers,
        verify=False,
        follow_redirects=True,
        proxy=proxy,
        event_hooks={'request': [_log_request]},
    )
