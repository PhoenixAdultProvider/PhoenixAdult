from __future__ import annotations

import time
from urllib.parse import urlsplit

import httpx2

from phoenixadult.utils.concurrency.single_flight import SingleFlight
from phoenixadult.utils.http.client import DEFAULT_UA, make_http
from phoenixadult.utils.logging.logger import logger

_HOST_CACHE_TTL = 30 * 60

_COOKIES: SingleFlight[str, dict[str, str]] = SingleFlight()


async def get_site_cookies(base_url: str) -> dict[str, str]:
    host = urlsplit(base_url).hostname or ''
    if not host:
        return {}

    async def _fetch() -> tuple[dict[str, str], float]:
        cookies: dict[str, str] = {}
        try:
            async with make_http() as client:
                await client.get(base_url, headers={'User-Agent': DEFAULT_UA})
                cookies = dict(client.cookies)
        except httpx2.HTTPError as err:
            logger.warn('siteCookies', f'GET {base_url} failed: {err}')
        return cookies, time.time() + _HOST_CACHE_TTL

    return await _COOKIES.get(host, _fetch) or {}
