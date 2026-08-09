from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from collections.abc import Awaitable, Callable
from urllib.parse import urljoin, urlsplit

import httpx2

from phoenixadult.utils.concurrency.single_flight import SingleFlight
from phoenixadult.utils.http.client import DEFAULT_UA, make_http
from phoenixadult.utils.logging.logger import logger

_HOST_CACHE_TTL = 30 * 60

_COOKIES: SingleFlight[str, dict[str, str]] = SingleFlight(serve_stale=False)

_BASE_HEADERS = {
    'User-Agent': DEFAULT_UA,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Upgrade-Insecure-Requests': '1',
}


def _same_site(a: str, b: str) -> bool:
    return a.lower().removeprefix('www.') == b.lower().removeprefix('www.')


def solve_pow(challenge: str, difficulty: int) -> int:
    target = 1 << (256 - difficulty)
    nonce = 0
    while True:
        h = hashlib.sha256(f'{challenge}:{nonce}'.encode()).digest()
        if int.from_bytes(h, 'big') < target:
            return nonce
        nonce += 1


async def get_verified_cookies(
    base_url: str, challenge_path: str = '/video/gallery', pace: Callable[[], Awaitable[None]] | None = None
) -> dict[str, str] | None:
    host = urlsplit(base_url).hostname or ''
    if not host:
        return None

    async def _fetch() -> tuple[dict[str, str], float] | None:
        base = base_url.rstrip('/')
        gallery_url = f'{base}/{challenge_path.strip("/")}'

        initial: dict[str, str] = {}
        try:
            async with make_http() as client:
                for _ in range(6):
                    if pace is not None:
                        await pace()
                    get_resp = await client.get(gallery_url, headers=_BASE_HEADERS, follow_redirects=False)
                    initial = dict(client.cookies)
                    loc = get_resp.headers.get('location', '')
                    if get_resp.status_code not in (301, 302, 303, 307, 308) or not loc:
                        break
                    nxt = urljoin(gallery_url, loc)
                    if not _same_site(urlsplit(nxt).hostname or '', host):
                        break
                    gallery_url = nxt
        except httpx2.HTTPError as err:
            logger.warn('pow', f'GET {gallery_url} failed: {err}')
            return None
        final = urlsplit(gallery_url)
        base = f'{final.scheme}://{final.netloc}'
        if get_resp.status_code == 429:
            logger.warn('pow', f'rate-limited on {gallery_url}')
            return None

        m = re.search(r'var\s+turnstileConfig\s*=\s*(\{.*?\});', get_resp.text, re.DOTALL)
        if not m:
            return initial, time.time() + _HOST_CACHE_TTL

        try:
            config = json.loads(m.group(1))
        except ValueError as err:
            logger.warn('pow', f'turnstileConfig JSON parse failed for {host}: {err}')
            return None

        t0 = time.time()
        nonce = await asyncio.to_thread(solve_pow, config['challenge'], config['difficulty'])
        logger.info('pow', f'{host}: solved difficulty={config["difficulty"]} nonce={nonce} in {round((time.time() - t0) * 1000)}ms')

        verify_url = f'{base}/turnstile/verify'
        payload = {
            'nonce': str(nonce),
            'timestamp': config['timestamp'],
            'difficulty': config['difficulty'],
            'environmentChecks': {
                'screenWidth': 1920,
                'screenHeight': 1080,
                'hasCanvas': True,
                'hasWebGL': True,
                'colorDepth': 24,
                'timezoneOffset': 300,
                'languages': 'en-US,en',
                'platform': 'Win32',
                'cookieEnabled': True,
            },
            'returnTo': config['returnTo'],
        }
        cookie_header = '; '.join(f'{k}={v}' for k, v in initial.items())
        post_headers = {**_BASE_HEADERS, 'Content-Type': 'application/json', 'Referer': gallery_url, 'Origin': base}
        if cookie_header:
            post_headers['Cookie'] = cookie_header

        try:
            if pace is not None:
                await pace()
            async with make_http() as client:
                post_resp = await client.post(verify_url, content=json.dumps(payload), headers=post_headers)
                verify_cookies = dict(client.cookies)
        except httpx2.HTTPError as err:
            logger.warn('pow', f'POST {verify_url} failed: {err}')
            return None
        if post_resp.status_code != 200:
            logger.warn('pow', f'verify returned {post_resp.status_code} for {host}')
            return None

        try:
            success = post_resp.json()
        except ValueError:
            success = None
        ok = success.get('success') if isinstance(success, dict) else False
        if not ok:
            logger.warn('pow', f'verify success=false for {host}: {json.dumps(success)}')
            return None

        merged = {**initial, **verify_cookies}
        return merged, time.time() + _HOST_CACHE_TTL

    return await _COOKIES.get(host, _fetch)
