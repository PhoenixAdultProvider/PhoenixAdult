from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx2

from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.concurrency.single_flight import SingleFlight
from phoenixadult.utils.http.client import DEFAULT_UA, make_http
from phoenixadult.utils.logging.logger import logger

_HOST_CACHE_TTL = 30 * 60
_MAX_DIFFICULTY = 26

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


_REDIRECTS = (301, 302, 303, 307, 308)
_MAX_HOPS = 6
_CONFIG_RE = re.compile(r'var\s+turnstileConfig\s*=\s*(\{.*?\});', re.DOTALL)
_ENVIRONMENT = {
    'screenWidth': 1920,
    'screenHeight': 1080,
    'hasCanvas': True,
    'hasWebGL': True,
    'colorDepth': 24,
    'timezoneOffset': 300,
    'languages': 'en-US,en',
    'platform': 'Win32',
    'cookieEnabled': True,
}

_Cached = tuple[dict[str, str], float]


def _verify_payload(config: dict[str, Any], nonce: int) -> dict[str, Any]:
    return {
        'nonce': str(nonce),
        'timestamp': config['timestamp'],
        'difficulty': config['difficulty'],
        'environmentChecks': _ENVIRONMENT,
        'returnTo': config['returnTo'],
    }


class _Challenge:
    def __init__(self, base_url: str, challenge_path: str, pace: Callable[[], Awaitable[None]] | None, host: str) -> None:
        self.gallery_url = f'{base_url.rstrip("/")}/{challenge_path.strip("/")}'
        self.pace = pace
        self.host = host
        self.cookies: dict[str, str] = {}

    async def _paced(self) -> None:
        if self.pace is not None:
            await self.pace()

    async def run(self) -> _Cached | None:
        page = await self._open_gallery()
        if page is None:
            return None
        match = _CONFIG_RE.search(page.text)
        if not match:
            return self.cookies, time.time() + _HOST_CACHE_TTL
        config = self._config(match.group(1))
        if config is None:
            return None
        nonce = await self._solve(config)
        verified = await self._verify(_verify_payload(config, nonce))
        return None if verified is None else ({**self.cookies, **verified}, time.time() + _HOST_CACHE_TTL)

    async def _open_gallery(self) -> httpx2.Response | None:
        try:
            async with make_http() as client:
                resp = await self._follow_same_site(client)
        except httpx2.HTTPError as err:
            logger.warn('pow', f'GET {self.gallery_url} failed: {err}')
            return None
        if resp.status_code == 429:
            logger.warn('pow', f'rate-limited on {self.gallery_url}')
            return None
        return resp

    async def _follow_same_site(self, client: httpx2.AsyncClient) -> httpx2.Response:
        for _ in range(_MAX_HOPS):
            await self._paced()
            resp = await client.get(self.gallery_url, headers=_BASE_HEADERS, follow_redirects=False)
            self.cookies = dict(client.cookies)
            loc = resp.headers.get('location', '')
            nxt = urljoin(self.gallery_url, loc) if resp.status_code in _REDIRECTS and loc else ''
            if not nxt or not _same_site(urlsplit(nxt).hostname or '', self.host):
                return resp
            self.gallery_url = nxt
        return resp

    def _config(self, raw: str) -> dict[str, Any] | None:
        try:
            config = json.loads(raw)
        except ValueError as err:
            logger.warn('pow', f'turnstileConfig JSON parse failed for {self.host}: {err}')
            return None
        difficulty = config.get('difficulty')
        if not isinstance(difficulty, int) or not 0 < difficulty <= _MAX_DIFFICULTY:
            logger.warn('pow', f'{self.host}: refusing proof-of-work difficulty {difficulty!r} (ceiling {_MAX_DIFFICULTY})')
            return None
        return dict(config)

    async def _solve(self, config: dict[str, Any]) -> int:
        t0 = time.time()
        nonce = await run_in('cpu', solve_pow, config['challenge'], config['difficulty'])
        logger.info('pow', f'{self.host}: solved difficulty={config["difficulty"]} nonce={nonce} in {round((time.time() - t0) * 1000)}ms')
        return nonce

    async def _verify(self, payload: dict[str, Any]) -> dict[str, str] | None:
        final = urlsplit(self.gallery_url)
        origin = f'{final.scheme}://{final.netloc}'
        verify_url = f'{origin}/turnstile/verify'
        headers = {**_BASE_HEADERS, 'Content-Type': 'application/json', 'Referer': self.gallery_url, 'Origin': origin}
        if self.cookies:
            headers['Cookie'] = '; '.join(f'{k}={v}' for k, v in self.cookies.items())
        try:
            await self._paced()
            async with make_http() as client:
                resp = await client.post(verify_url, content=json.dumps(payload), headers=headers)
                cookies = dict(client.cookies)
        except httpx2.HTTPError as err:
            logger.warn('pow', f'POST {verify_url} failed: {err}')
            return None
        return cookies if self._verified(resp) else None

    def _verified(self, resp: httpx2.Response) -> bool:
        if resp.status_code != 200:
            logger.warn('pow', f'verify returned {resp.status_code} for {self.host}')
            return False
        try:
            body = resp.json()
        except ValueError:
            body = None
        if isinstance(body, dict) and body.get('success'):
            return True
        logger.warn('pow', f'verify success=false for {self.host}: {json.dumps(body)}')
        return False


async def get_verified_cookies(
    base_url: str, challenge_path: str = '/video/gallery', pace: Callable[[], Awaitable[None]] | None = None
) -> dict[str, str] | None:
    host = urlsplit(base_url).hostname or ''
    if not host:
        return None
    return await _COOKIES.get(host, _Challenge(base_url, challenge_path, pace, host).run)
