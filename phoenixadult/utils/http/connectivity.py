from __future__ import annotations

import asyncio
import contextlib
import time
from contextvars import ContextVar

from phoenixadult.config.env import env

_failures: ContextVar[list[str] | None] = ContextVar('transport_failures', default=None)

_PROBE_TARGETS = (('1.1.1.1', 443), ('8.8.8.8', 443))
_PROBE_TIMEOUT = 3.0
_PROBE_TTL = 15.0
_probe_cache: tuple[float, bool] | None = None


def begin_transport_watch() -> None:
    _failures.set([])


def note_transport_failure(detail: str) -> None:
    sink = _failures.get()
    if sink is not None:
        sink.append(detail)


def transport_failures() -> list[str]:
    return list(_failures.get() or ())


async def _probe_once() -> bool:
    for host, port in _PROBE_TARGETS:
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), _PROBE_TIMEOUT)
        except (OSError, TimeoutError):
            continue
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()
        return True
    return False


async def internet_reachable() -> bool:
    global _probe_cache
    if (env.https_proxy or '').strip():
        return True
    now = time.monotonic()
    if _probe_cache is not None and now - _probe_cache[0] < _PROBE_TTL:
        return _probe_cache[1]
    result = await _probe_once()
    _probe_cache = (now, result)
    return result
