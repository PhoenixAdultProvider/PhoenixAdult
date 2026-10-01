from __future__ import annotations

import asyncio
import hashlib
import io
import time
import weakref
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx2
from cachetools import LRUCache, TLRUCache, TTLCache
from PIL import Image, ImageFile

from phoenixadult.config.env import env
from phoenixadult.config.env_catalog import parse_bytes
from phoenixadult.utils.concurrency.coalescer import Coalescer
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.http.client import DEFAULT_UA, make_http, read_capped
from phoenixadult.utils.http.headers import sanitize_header
from phoenixadult.utils.http.impersonate import impersonate_get_bytes
from phoenixadult.utils.http.pinned_fetch import fetch_pinned
from phoenixadult.utils.images.ext import is_image_content_type
from phoenixadult.utils.logging.logger import logger

_DEFAULT_MAX_BYTES = 20 * 1024 * 1024
_CACHE_TTL = 60 * 60
_CACHE_MAX_TOTAL_BYTES = 256 * 1024 * 1024
_MAX_IMAGE_PIXELS = 80 * 1024 * 1024

Image.MAX_IMAGE_PIXELS = _MAX_IMAGE_PIXELS

_PROBE_TIMEOUT = 4.0
_PROBE_HEAD_BYTES = 64 * 1024
_DIMS_TTL = 60 * 60
_DIMS_MISS_TTL = 300.0
_DIMS_CACHE_MAX = 8192

_shared_image_clients: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, httpx2.AsyncClient] = weakref.WeakKeyDictionary()
_shared_probe_clients: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, httpx2.AsyncClient] = weakref.WeakKeyDictionary()


def _image_client() -> httpx2.AsyncClient:
    loop = asyncio.get_running_loop()
    client = _shared_image_clients.get(loop)
    if client is None:
        client = make_http(timeout=10.0, max_redirects=3)
        _shared_image_clients[loop] = client
    return client


def _probe_client() -> httpx2.AsyncClient:
    loop = asyncio.get_running_loop()
    client = _shared_probe_clients.get(loop)
    if client is None:
        client = make_http(timeout=_PROBE_TIMEOUT, max_redirects=3)
        _shared_probe_clients[loop] = client
    return client


@dataclass
class ImageEntry:
    data: bytes
    content_type: str
    cached_at: float
    width: int
    height: int
    solid: bool = False


_cache: TTLCache[str, ImageEntry] = TTLCache(maxsize=_CACHE_MAX_TOTAL_BYTES, ttl=_CACHE_TTL, getsizeof=lambda e: len(e.data))


def _dims_ttu(_key: str, dims: tuple[int, int] | None, now: float) -> float:
    return now + (_DIMS_TTL if dims else _DIMS_MISS_TTL)


_dims_cache: TLRUCache[str, tuple[int, int] | None] = TLRUCache(maxsize=_DIMS_CACHE_MAX, ttu=_dims_ttu)
_DIMS_MISSING: tuple[int, int] = (-1, -1)


def max_image_bytes() -> int:
    parsed = parse_bytes(env.image_max_bytes_raw or '')
    if parsed is None:
        return _DEFAULT_MAX_BYTES
    n = int(parsed)
    return n if n > 0 else _DEFAULT_MAX_BYTES


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

    async with client.stream('GET', url, headers=headers) as resp:
        resp.raise_for_status()
        content_type = resp.headers.get('content-type', '')
        if not is_image_content_type(content_type):
            raise ValueError(f'non-image content-type "{content_type}" from {url}')
        data = await read_capped(resp, max_image_bytes())
    return data, content_type


def _accept_image_response(resp: httpx2.Response, url: str) -> tuple[bytes, str]:
    resp.raise_for_status()
    content_type = resp.headers.get('content-type', '')
    data = resp.content
    if not is_image_content_type(content_type):
        raise ValueError(f'non-image content-type "{content_type}" ({len(data)} bytes) from {url}')
    if len(data) > max_image_bytes():
        raise ValueError(f'image too large ({len(data)} bytes > {max_image_bytes()}) at {url}')
    return data, content_type


async def _get_once_pinned(url: str, referer: str | None, cookie: str | None) -> tuple[bytes, str]:
    headers = {'User-Agent': DEFAULT_UA}
    if referer:
        headers['Referer'] = sanitize_header(referer)
    if cookie:
        headers['Cookie'] = sanitize_header(cookie)
    resp = await fetch_pinned(url, headers, max_bytes=max_image_bytes())
    return _accept_image_response(resp, url)


_byte_digests: LRUCache[str, str] = LRUCache(maxsize=_DIMS_CACHE_MAX)
_pixel_digests: LRUCache[str, str] = LRUCache(maxsize=_DIMS_CACHE_MAX)


def _sha1(data: bytes) -> str:
    return hashlib.sha1(data, usedforsecurity=False).hexdigest()


def _decode_pixels(data: bytes) -> str:
    with Image.open(io.BytesIO(data)) as img:
        return _sha1(img.convert('RGB').tobytes())


def cache_key(url: str, cookies: list[str] | None = None) -> str:
    return f'{url}\x00{"; ".join(cookies)}' if cookies and not _is_data18_host(url) else url


async def content_digest(url: str, cookies: list[str] | None = None) -> str | None:
    key = cache_key(url, cookies)
    if (hit := _byte_digests.get(key)) is not None:
        return hit
    entry = _cache.get(key)
    if entry is None:
        return None
    digest = await run_in('image', _sha1, entry.data)
    _byte_digests[key] = digest
    return digest


async def pixel_digest(url: str, cookies: list[str] | None = None) -> str | None:
    key = cache_key(url, cookies)
    if (hit := _pixel_digests.get(key)) is not None:
        return hit
    entry = _cache.get(key)
    if entry is None:
        return None
    try:
        digest = await run_in('image', _decode_pixels, entry.data)
    except Exception as err:  # noqa: BLE001 - an undecodable image simply is not deduped
        logger.debug(f'pixel digest failed for {url}: {err!r}')
        return None
    _pixel_digests[key] = digest
    return digest


SOLID_SPREAD = 4
_SOLID_DRAFT = 160


_ROTATE_TRANSPOSE = {90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180, 270: Image.Transpose.ROTATE_90}


def rotate_image_bytes(data: bytes, degrees: int) -> bytes:
    transpose = _ROTATE_TRANSPOSE.get(degrees % 360)
    if transpose is None:
        return data
    with Image.open(io.BytesIO(data)) as img:
        fmt = img.format or 'JPEG'
        rotated = img.transpose(transpose)
    buf = io.BytesIO()
    if fmt == 'JPEG':
        rotated = rotated.convert('RGB') if rotated.mode not in ('RGB', 'L') else rotated
        rotated.save(buf, format='JPEG', quality=95)
    else:
        rotated.save(buf, format=fmt)
    return buf.getvalue()


def is_solid(img: Image.Image) -> bool:
    extrema = img.getextrema()
    bands = extrema if isinstance(extrema[0], tuple) else (extrema,)
    return all(high - low <= SOLID_SPREAD for low, high in bands if low is not None and high is not None)


def _decode_dims(data: bytes) -> tuple[int, int, bool]:
    with Image.open(io.BytesIO(data)) as img:
        width, height = img.size
        img.draft(None, (_SOLID_DRAFT, _SOLID_DRAFT))
        probe: Image.Image = img.convert('RGBA' if 'transparency' in img.info else 'RGB') if img.mode == 'P' else img
        return int(width), int(height), is_solid(probe)


_coalesce: Coalescer[str, ImageEntry] = Coalescer()


async def fetch_image(url: str, configured_referers: list[str] | None = None, configured_cookies: list[str] | None = None, pinned: bool = False) -> ImageEntry:
    key = cache_key(url, configured_cookies)
    cached = _cache.get(key)
    if cached:
        return cached
    return await _coalesce.run(key, lambda: _fetch_image(url, configured_referers, configured_cookies, pinned))


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
        width, height, solid = await run_in('image', _decode_dims, data)
    except Exception:  # noqa: BLE001 - undecodable image still served, just unsized
        width, height, solid = 0, 0, False

    entry = ImageEntry(data=data, content_type=content_type, cached_at=time.time(), width=width, height=height, solid=solid)
    _cache[cache_key(url, configured_cookies)] = entry
    return entry


def _dims_cache_get(url: str) -> tuple[bool, tuple[int, int] | None]:
    hit = _dims_cache.get(url, _DIMS_MISSING)
    if hit is _DIMS_MISSING:
        return False, None
    return True, hit


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
            async with client.stream('GET', url, headers=headers) as resp:
                responded = True
                absent = resp.status_code in (404, 410)
                resp.raise_for_status()
                if not is_image_content_type(resp.headers.get('content-type', '')):
                    continue
                head = await read_capped(resp, _PROBE_HEAD_BYTES, truncate=True)
            if dims := await run_in('image', _dims_from_head, head):
                return dims, True
        except Exception as err:  # noqa: BLE001 - `responded` already records whether the host answered at all
            logger.debug(f'dimension probe failed for {url}: {err!r}')
    return None, responded and not absent


async def fetch_dimensions(url: str, referers: list[str] | None = None, cookies: list[str] | None = None) -> dict[str, int] | None:
    cached_hit, cached_dims = _dims_cache_get(url)
    if cached_hit:
        return {'width': cached_dims[0], 'height': cached_dims[1]} if cached_dims else None

    if (entry := _cache.get(cache_key(url, cookies))) is not None and entry.width > 0 and entry.height > 0:
        _dims_cache[url] = (entry.width, entry.height)
        return {'width': entry.width, 'height': entry.height}

    if not env.metadata_cache_enabled:
        probed, responded = await _probe_dims(url, referers, cookies)
        if probed:
            _dims_cache[url] = probed
            return {'width': probed[0], 'height': probed[1]}
        if not responded:
            _dims_cache[url] = None
            return None

    try:
        entry = await fetch_image(url, referers, cookies)
    except Exception as err:  # noqa: BLE001
        logger.debug(f'fetchDimensions failed for {url}: {err!r}')
        _dims_cache[url] = None
        return None
    if entry.width <= 0 or entry.height <= 0:
        _dims_cache[url] = None
        return None
    _dims_cache[url] = (entry.width, entry.height)
    return {'width': entry.width, 'height': entry.height}
