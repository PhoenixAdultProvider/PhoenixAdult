from __future__ import annotations

import asyncio
import contextlib
import time
from contextvars import ContextVar

from phoenixadult.config.env import env
from phoenixadult.utils.concurrency.single_flight import SingleFlight
from phoenixadult.utils.logging.logger import logger

_failures: ContextVar[list[str] | None] = ContextVar('transport_failures', default=None)

_PROBE_TARGETS = (('1.1.1.1', 443), ('8.8.8.8', 443))
_PROBE_HOSTNAME = 'one.one.one.one'
_PROBE_TIMEOUT = 3.0
_PROBE_TTL = 15.0
_probe = SingleFlight[str, bool](serve_stale=False)
_down = False


def begin_transport_watch() -> None:
    _failures.set([])


def note_transport_failure(detail: str) -> None:
    sink = _failures.get()
    if sink is not None:
        sink.append(detail)


def transport_failures() -> list[str]:
    return list(_failures.get() or ())


async def _connects() -> bool:
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


async def _resolves() -> bool:
    try:
        return bool(await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(_PROBE_HOSTNAME, 443), _PROBE_TIMEOUT))
    except OSError:
        return False


async def _probe_once() -> bool:
    return await _connects() and await _resolves()


async def _measure() -> tuple[bool, float]:
    global _down
    reachable = await _probe_once()
    if _down == reachable:
        if reachable:
            logger.info('network', 'Network is back; outbound requests resume')
        else:
            logger.warn('network', 'Network is down (no route or no DNS); outbound requests fail fast until it recovers')
    _down = not reachable
    return reachable, time.time() + _PROBE_TTL


def network_down() -> bool:
    return _down


async def internet_reachable() -> bool:
    if (env.https_proxy or '').strip():
        return True
    return bool(await _probe.get('internet', _measure))


async def network_usable() -> bool:
    return not _down or await internet_reachable()


def reset_network_state() -> None:
    global _down
    _down = False
    _probe.clear()
