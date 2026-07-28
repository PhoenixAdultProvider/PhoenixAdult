from __future__ import annotations

from typing import Any

import httpx2

from phoenixadult.config.env import env
from phoenixadult.utils.logging.logger import logger

DEFAULT_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'


def _proxy_url() -> str | None:
    raw = env.https_proxy
    return raw.strip() if raw and raw.strip() else None


async def _log_request(request: httpx2.Request) -> None:
    logger.http(f'Requesting {request.method.upper()} "{request.url}"')


def make_http(extra_headers: dict[str, str] | None = None, **overrides: Any) -> httpx2.AsyncClient:
    opts: dict[str, Any] = {
        'timeout': 15.0,
        'headers': {'User-Agent': DEFAULT_UA, **(extra_headers or {})},
        'verify': False,
        'follow_redirects': True,
        'proxy': _proxy_url(),
        'event_hooks': {'request': [_log_request]},
    }
    opts.update(overrides)
    return httpx2.AsyncClient(**opts)
