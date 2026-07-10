from __future__ import annotations

import asyncio
import io
import time
from collections import OrderedDict
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx2
from PIL import Image

from app.config.env import env
from app.utils.concurrency.coalescer import Coalescer
from app.utils.http.client import DEFAULT_UA, make_http
from app.utils.http.headers import sanitize_header
from app.utils.http.impersonate import impersonate_get_bytes
from app.utils.http.pinned_fetch import fetch_pinned
from app.utils.http.ssrf_guard import is_blocked_hostname
from app.utils.logging.logger import logger

_DEFAULT_MAX_BYTES = 20 * 1024 * 1024
_CACHE_TTL = 60 * 60  # seconds
_CACHE_MAX_TOTAL_BYTES = 256 * 1024 * 1024


@dataclass
class ImageEntry:
    data: bytes
    content_type: str
    cached_at: float
    width: int
    height: int


_cache: OrderedDict[str, ImageEntry] = OrderedDict()
_cache_total_bytes = 0


def _cache_get(url: str) -> ImageEntry | None:
    global _cache_total_bytes
    entry = _cache.get(url)
    if entry is None:
        return None
    if time.time() - entry.cached_at >= _CACHE_TTL:
        del _cache[url]
        _cache_total_bytes -= len(entry.data)
        return None
    _cache.move_to_end(url)
    return entry


def _cache_put(url: str, entry: ImageEntry) -> None:
    global _cache_total_bytes
    old = _cache.pop(url, None)
    if old is not None:
        _cache_total_bytes -= len(old.data)
    _cache[url] = entry
    _cache_total_bytes += len(entry.data)
    now = time.time()
    for key in [k for k, v in _cache.items() if now - v.cached_at >= _CACHE_TTL]:
        _cache_total_bytes -= len(_cache.pop(key).data)
    while _cache_total_bytes > _CACHE_MAX_TOTAL_BYTES and _cache:
        _, evicted = _cache.popitem(last=False)
        _cache_total_bytes -= len(evicted.data)


def _max_bytes() -> int:
    try:
        raw = int(env.image_max_bytes_raw or '')
    except ValueError:
        return _DEFAULT_MAX_BYTES
    return raw if raw > 0 else _DEFAULT_MAX_BYTES


def _referers_for(url: str, configured: list[str] | None) -> list[str | None]:
    if configured:
        return [*configured, None]
    host = ''
    try:
        host = (urlsplit(url).hostname or '').lower()
    except ValueError:
        pass
    if 'data18.com' in host or 'dt18.com' in host:
        return ['http://i.dt18.com', 'https://www.data18.com']
    return [None]


async def _get_once(client: httpx2.AsyncClient, url: str, referer: str | None, cookie: str | None) -> tuple[bytes, str]:
    headers = {'User-Agent': DEFAULT_UA}
    if referer:
        headers['Referer'] = sanitize_header(referer)
    if cookie:
        headers['Cookie'] = sanitize_header(cookie)

    resp = await client.get(url, headers=headers)
    for redirect in resp.history:
        loc = redirect.headers.get('location', '')
        host = urlsplit(loc).hostname
        if host and is_blocked_hostname(host):
            raise ValueError(f'blocked redirect to {host}')
    return _accept_image_response(resp, url)


def _accept_image_response(resp: httpx2.Response, url: str) -> tuple[bytes, str]:
    resp.raise_for_status()
    content_type = resp.headers.get('content-type', '')
    data = resp.content
    if not content_type.lower().startswith('image/'):
        raise ValueError(f'non-image content-type "{content_type}" ({len(data)} bytes) from {url}')
    if len(data) > _max_bytes():
        raise ValueError(f'image too large ({len(data)} bytes > {_max_bytes()}) at {url}')
    return data, content_type


async def _get_once_pinned(url: str, referer: str | None, cookie: str | None) -> tuple[bytes, str]:
    headers = {'User-Agent': DEFAULT_UA}
    if referer:
        headers['Referer'] = sanitize_header(referer)
    if cookie:
        headers['Cookie'] = sanitize_header(cookie)
    resp = await fetch_pinned(url, headers)
    return _accept_image_response(resp, url)


def _decode_dims(data: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as img:
        width, height = img.size
        return int(width), int(height)


_coalesce: Coalescer[str, ImageEntry] = Coalescer()


async def fetch_image(url: str, configured_referers: list[str] | None = None, configured_cookies: list[str] | None = None, pinned: bool = False) -> ImageEntry:
    cached = _cache_get(url)
    if cached:
        return cached
    # Coalesce concurrent fetches of the same URL (metadata + /images probe the same set).
    return await _coalesce.run(url, lambda: _fetch_image(url, configured_referers, configured_cookies, pinned))


async def _fetch_image(url: str, configured_referers: list[str] | None = None, configured_cookies: list[str] | None = None, pinned: bool = False) -> ImageEntry:
    referers = _referers_for(url, configured_referers)
    cookie_header = '; '.join(configured_cookies) if configured_cookies else None
    last_err: Exception | None = None
    payload: tuple[bytes, str] | None = None

    if pinned:
        for referer in referers:
            try:
                payload = await _get_once_pinned(url, referer, cookie_header)
                break
            except Exception as err:  # noqa: BLE001 - retry on any per-referer failure
                last_err = err
                logger.debug(f'fetchImage retry (pinned): Referer="{referer or "(none)"}" failed for {url}: {err}')
    else:
        async with make_http(timeout=10.0, max_redirects=3) as client:
            for referer in referers:
                try:
                    payload = await _get_once(client, url, referer, cookie_header)
                    break
                except Exception as err:  # noqa: BLE001 - retry on any per-referer failure
                    last_err = err
                    logger.debug(f'fetchImage retry: Referer="{referer or "(none)"}" failed for {url}: {err}')

    if payload is None and not pinned:
        # Cloudflare-gated hosts (e.g. IAFD headshots) 403 the plain client — retry the
        # binary fetch via curl_cffi impersonation. Send Referer/Cookie only; a UA
        # override would break the impersonated TLS fingerprint and get 403'd again.
        # Pinned (proxy) fetches never take this path: curl resolves independently,
        # which would reopen the DNS-rebind hole.
        hdrs: dict[str, str] = {}
        ref = next((r for r in referers if r), None)
        if ref:
            hdrs['Referer'] = sanitize_header(ref)
        if cookie_header:
            hdrs['Cookie'] = sanitize_header(cookie_header)
        got = await impersonate_get_bytes(url, hdrs or None)
        if got is not None:
            logger.debug(f'fetchImage: impersonate fetched {url}')
            payload = got

    if payload is None:
        raise last_err or ValueError(f'All Referer attempts failed for {url}')

    data, content_type = payload
    try:
        width, height = await asyncio.to_thread(_decode_dims, data)
    except Exception:  # noqa: BLE001 - undecodable image still served, just unsized
        width, height = 0, 0

    entry = ImageEntry(data=data, content_type=content_type, cached_at=time.time(), width=width, height=height)
    _cache_put(url, entry)
    return entry


async def fetch_dimensions(url: str, referers: list[str] | None = None, cookies: list[str] | None = None) -> dict[str, int] | None:
    try:
        entry = await fetch_image(url, referers, cookies)
    except Exception as err:  # noqa: BLE001
        logger.debug(f'fetchDimensions failed for {url}: {err}')
        return None
    if entry.width <= 0 or entry.height <= 0:
        return None
    return {'width': entry.width, 'height': entry.height}
