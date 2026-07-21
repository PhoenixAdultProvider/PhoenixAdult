from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from app.utils.logging.logger import logger

_MAX_PENDING = 500

_queue: asyncio.Queue[tuple[str, Callable[[], Awaitable[object]]]] | None = None
_pending: set[str] = set()
_worker: asyncio.Task[None] | None = None
_loop_id: int | None = None


def _ensure_loop() -> None:
    """Bind the queue/worker to the running loop; a new loop (tests) resets state."""
    global _queue, _pending, _worker, _loop_id
    loop_id = id(asyncio.get_running_loop())
    if _loop_id != loop_id:
        _loop_id = loop_id
        _queue = asyncio.Queue()
        _pending = set()
        _worker = None


def enqueue(key: str, job: Callable[[], Awaitable[object]]) -> bool:
    """Queue a background job for the single sequential worker, deduped by key; False
    when the key is already pending or the queue is full."""
    global _worker
    _ensure_loop()
    assert _queue is not None
    if key in _pending or len(_pending) >= _MAX_PENDING:
        return False
    _pending.add(key)
    _queue.put_nowait((key, job))
    if _worker is None or _worker.done():
        _worker = asyncio.get_running_loop().create_task(_run())
    logger.info('scrape-queue', f'queued background scrape {key} ({len(_pending)} pending)')
    return True


def is_pending(key: str) -> bool:
    return key in _pending


def pending_count() -> int:
    return len(_pending)


async def _run() -> None:
    assert _queue is not None
    while True:
        try:
            key, job = _queue.get_nowait()
        except asyncio.QueueEmpty:
            return
        try:
            await job()
            logger.info('scrape-queue', f'background scrape finished {key} ({len(_pending) - 1} pending)')
        except Exception as err:  # noqa: BLE001 - one failed job never kills the worker
            logger.warn('scrape-queue', f'background scrape failed {key}: {err!r}')
        finally:
            _pending.discard(key)
