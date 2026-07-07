from __future__ import annotations

import time
from urllib.parse import urlsplit

import httpx2

from app.utils.concurrency.single_flight import SingleFlight
from app.utils.http.client import DEFAULT_UA, make_http
from app.utils.logging.logger import logger

_HOST_CACHE_TTL = 30 * 60  # seconds

_COOKIES: SingleFlight[str, dict[str, str]] = SingleFlight()


def parse_set_cookie(lines: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in lines:
        first = line.split(';', 1)[0]
        eq = first.find('=')
        if eq > 0:
            out[first[:eq].strip()] = first[eq + 1 :].strip()
    return out


async def get_site_cookies(base_url: str) -> dict[str, str]:
    host = urlsplit(base_url).hostname or ''
    if not host:
        return {}

    async def _fetch() -> tuple[dict[str, str], float]:
        cookies: dict[str, str] = {}
        try:
            async with make_http() as client:
                r = await client.get(base_url, headers={'User-Agent': DEFAULT_UA})
            cookies = parse_set_cookie(r.headers.get_list('set-cookie'))
        except httpx2.HTTPError as err:
            logger.warn('siteCookies', f'GET {base_url} failed: {err}')
        return cookies, time.time() + _HOST_CACHE_TTL

    return await _COOKIES.get(host, _fetch) or {}
