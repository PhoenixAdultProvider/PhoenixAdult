from __future__ import annotations

import asyncio
import io
import time
from collections import OrderedDict
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx2
from PIL import Image, ImageFile

from phoenixadult.config.env import env
from phoenixadult.utils.concurrency.coalescer import Coalescer
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.http.client import DEFAULT_UA, make_http
from phoenixadult.utils.http.headers import sanitize_header
from phoenixadult.utils.http.impersonate import impersonate_get_bytes
from phoenixadult.utils.http.pinned_fetch import fetch_pinned
from phoenixadult.utils.http.ssrf_guard import is_blocked_hostname
from phoenixadult.utils.images.ext import is_image_content_type
from phoenixadult.utils.logging.logger import logger

_DEFAULT_MAX_BYTES = 20 * 1024 * 1024
_CACHE_TTL = 60 * 60
_CACHE_MAX_TOTAL_BYTES = 256 * 1024 * 1024

_PROBE_TIMEOUT = 4.0
_PROBE_HEAD_BYTES = 64 * 1024
_DIMS_TTL = 60 * 60
_DIMS_MISS_TTL = 300.0
_DIMS_CACHE_MAX = 8192

_shared_image_clients: dict[int, httpx2.AsyncClient] = {}
_shared_probe_clients: dict[int, httpx2.AsyncClient] = {}


def _image_client() -> httpx2.AsyncClient:
    loop_id = id(asyncio.get_running_loop())
    client = _shared_image_clients.get(loop_id)
    if client is None:
        client = make_http(timeout=10.0, max_redirects=3)
        _shared_image_clients[loop_id] = client
    return client


def _probe_client() -> httpx2.AsyncClient:
    loop_id = id(asyncio.get_running_loop())
    client = _shared_probe_clients.get(loop_id)
    if client is None:
        client = make_http(timeout=_PROBE_TIMEOUT, max_redirects=3)
        _shared_probe_clients[loop_id] = client
    return client


@dataclass
class ImageEntry:
    data: bytes
    content_type: str
    cached_at: float
    width: int
    height: int


_cache: OrderedDict[str, ImageEntry] = OrderedDict()
_cache_total_bytes = 0
_dims_cache: OrderedDict[str, tuple[float, tuple[int, int] | None]] = OrderedDict()


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
    while _cache_total_bytes > _CACHE_MAX_TOTAL_BYTES and _cache:
        _, evicted = _cache.popitem(last=False)
        _cache_total_bytes -= len(evicted.data)


def _max_bytes() -> int:
    try:
        raw = int(env.image_max_bytes_raw or '')
    except ValueError:
        return _DEFAULT_MAX_BYTES
    return raw if raw > 0 else _DEFAULT_MAX_BYTES


def _is_data18_host(url: str) -> bool:
    try:
        host = (urlsplit(url).hostname or '').lower()
    except ValueError:
        return False
    return 'data18.com' in host or 'dt18.com' in host


def _referers_for(url: str, configured: list[str] | None) -> list[str | None]:
    if _is_data18_host(url):
        return ['http://i.dt18.com', 'https://www.data18.com']
    if configured:
        return [*configured, None]
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
    if not is_image_content_type(content_type):
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
    return await _coalesce.run(url, lambda: _fetch_image(url, configured_referers, configured_cookies, pinned))


async def _fetch_image(url: str, configured_referers: list[str] | None = None, configured_cookies: list[str] | None = None, pinned: bool = False) -> ImageEntry:
    referers = _referers_for(url, configured_referers)
    cookie_header = '; '.join(configured_cookies) if configured_cookies and not _is_data18_host(url) else None
    last_err: Exception | None = None
    payload: tuple[bytes, str] | None = None
    failed_attempts = 0
    won_referer: str | None = None

    if pinned:
        for referer in referers:
            try:
                payload = await _get_once_pinned(url, referer, cookie_header)
                won_referer = referer
                break
            except Exception as err:  # noqa: BLE001 - retry on any per-referer failure
                last_err = err
                failed_attempts += 1
    else:
        client = _image_client()
        for referer in referers:
            try:
                payload = await _get_once(client, url, referer, cookie_header)
                won_referer = referer
                break
            except Exception as err:  # noqa: BLE001 - retry on any per-referer failure
                last_err = err
                failed_attempts += 1

    if payload is None and not pinned:
        hdrs: dict[str, str] = {}
        ref = next((r for r in referers if r), None)
        if ref:
            hdrs['Referer'] = sanitize_header(ref)
        if cookie_header:
            hdrs['Cookie'] = sanitize_header(cookie_header)
        got = await impersonate_get_bytes(url, hdrs or None)
        if got is not None:
            won_referer = 'impersonate'
            payload = got

    if payload is None:
        raise last_err or ValueError(f'All Referer attempts failed for {url}')
    if failed_attempts:
        logger.debug(f'fetchImage: {url} succeeded via {won_referer or "(no referer)"} after {failed_attempts} failed attempt(s)')

    data, content_type = payload
    try:
        width, height = await run_in('image', _decode_dims, data)
    except Exception:  # noqa: BLE001 - undecodable image still served, just unsized
        width, height = 0, 0

    entry = ImageEntry(data=data, content_type=content_type, cached_at=time.time(), width=width, height=height)
    _cache_put(url, entry)
    return entry


def _dims_cache_get(url: str) -> tuple[bool, tuple[int, int] | None]:
    hit = _dims_cache.get(url)
    if hit is None:
        return False, None
    stored_at, dims = hit
    if time.time() - stored_at >= (_DIMS_TTL if dims else _DIMS_MISS_TTL):
        del _dims_cache[url]
        return False, None
    _dims_cache.move_to_end(url)
    return True, dims


def _dims_cache_put(url: str, dims: tuple[int, int] | None) -> None:
    _dims_cache.pop(url, None)
    _dims_cache[url] = (time.time(), dims)
    while len(_dims_cache) > _DIMS_CACHE_MAX:
        _dims_cache.popitem(last=False)


def _dims_from_head(data: bytes) -> tuple[int, int] | None:
    parser = ImageFile.Parser()
    parser.feed(data)
    if parser.image is None:
        return None
    width, height = parser.image.size
    return (int(width), int(height)) if width > 0 and height > 0 else None


async def _probe_dims(url: str, referers: list[str] | None, cookies: list[str] | None) -> tuple[tuple[int, int] | None, bool]:
    client = _probe_client()
    cookie_header = '; '.join(cookies) if cookies and not _is_data18_host(url) else None
    responded = False
    absent = False
    for referer in _referers_for(url, referers):
        headers = {'User-Agent': DEFAULT_UA, 'Range': f'bytes=0-{_PROBE_HEAD_BYTES - 1}'}
        if referer:
            headers['Referer'] = sanitize_header(referer)
        if cookie_header:
            headers['Cookie'] = sanitize_header(cookie_header)
        try:
            resp = await client.get(url, headers=headers)
            responded = True
            absent = resp.status_code in (404, 410)
            for redirect in resp.history:
                host = urlsplit(redirect.headers.get('location', '')).hostname
                if host and is_blocked_hostname(host):
                    raise ValueError(f'blocked redirect to {host}')
            resp.raise_for_status()
            if not is_image_content_type(resp.headers.get('content-type', '')):
                continue
            if dims := await run_in('image', _dims_from_head, resp.content):
                return dims, True
        except Exception as err:  # noqa: BLE001 - `responded` already records whether the host answered at all
            logger.debug(f'dimension probe failed for {url}: {err!r}')
    return None, responded and not absent


async def fetch_dimensions(url: str, referers: list[str] | None = None, cookies: list[str] | None = None) -> dict[str, int] | None:
    cached_hit, cached_dims = _dims_cache_get(url)
    if cached_hit:
        return {'width': cached_dims[0], 'height': cached_dims[1]} if cached_dims else None

    if (entry := _cache_get(url)) is not None and entry.width > 0 and entry.height > 0:
        _dims_cache_put(url, (entry.width, entry.height))
        return {'width': entry.width, 'height': entry.height}

    probed, responded = await _probe_dims(url, referers, cookies)
    if probed:
        _dims_cache_put(url, probed)
        return {'width': probed[0], 'height': probed[1]}
    if not responded:
        _dims_cache_put(url, None)
        return None

    try:
        entry = await fetch_image(url, referers, cookies)
    except Exception as err:  # noqa: BLE001
        logger.debug(f'fetchDimensions failed for {url}: {err!r}')
        _dims_cache_put(url, None)
        return None
    if entry.width <= 0 or entry.height <= 0:
        _dims_cache_put(url, None)
        return None
    _dims_cache_put(url, (entry.width, entry.height))
    return {'width': entry.width, 'height': entry.height}
