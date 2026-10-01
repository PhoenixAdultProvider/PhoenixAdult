from __future__ import annotations

import asyncio
import weakref
from typing import Any

import httpx2

from phoenixadult.config.env import env
from phoenixadult.utils.http.connectivity import note_transport_failure
from phoenixadult.utils.http.ssrf_guard import guard_target
from phoenixadult.utils.logging.context import current_scrape_phase
from phoenixadult.utils.logging.logger import logger

DEFAULT_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'


def configured_https_proxy() -> str | None:
    raw = env.https_proxy
    return raw.strip() if raw and raw.strip() else None


async def _log_request(request: httpx2.Request) -> None:
    line = f'Requesting {request.method.upper()} "{request.url}"'
    phase = current_scrape_phase()
    if phase:
        logger.info(phase, line)
    else:
        logger.http(line)


async def _guard_redirect(response: httpx2.Response) -> None:
    if response.has_redirect_location:
        location = response.headers.get('location', '')
        if location:
            target = str(response.url.join(location))
            try:
                await guard_target(target)
            except ValueError as err:
                raise ValueError(f'blocked redirect to {target}: {err}') from err


class _WatchedTransport(httpx2.AsyncHTTPTransport):
    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        try:
            return await super().handle_async_request(request)
        except httpx2.TransportError as err:
            note_transport_failure(f'{request.url.host}: {type(err).__name__}')
            raise


def make_http(extra_headers: dict[str, str] | None = None, **overrides: Any) -> httpx2.AsyncClient:
    opts: dict[str, Any] = {
        'timeout': 15.0,
        'headers': {'User-Agent': DEFAULT_UA, **(extra_headers or {})},
        'verify': False,
        'follow_redirects': True,
        'proxy': configured_https_proxy(),
        'event_hooks': {'request': [_log_request]},
    }
    opts.update(overrides)
    if opts.get('follow_redirects', True):
        opts['event_hooks'].setdefault('response', []).append(_guard_redirect)
    if 'transport' not in opts:
        transport_opts = {'verify': opts.pop('verify'), 'proxy': opts.pop('proxy')}
        if 'limits' in opts:
            transport_opts['limits'] = opts.pop('limits')
        opts['transport'] = _WatchedTransport(**transport_opts)
    return httpx2.AsyncClient(**opts)


_shared_clients: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, httpx2.AsyncClient]] = weakref.WeakKeyDictionary()


def shared_http(tag: str, **overrides: Any) -> httpx2.AsyncClient:
    loop = asyncio.get_running_loop()
    by_tag = _shared_clients.setdefault(loop, {})
    client = by_tag.get(tag)
    if client is None:
        client = make_http(**overrides)
        by_tag[tag] = client
    return client


async def read_capped(response: httpx2.Response, limit: int, *, truncate: bool = False) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        if total + len(chunk) > limit:
            if not truncate:
                raise ValueError(f'response from {response.url} exceeds {limit} bytes')
            chunks.append(chunk[: limit - total])
            break
        total += len(chunk)
        chunks.append(chunk)
    return b''.join(chunks)
