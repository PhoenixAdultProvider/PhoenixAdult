from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any


class Coalescer[K, V]:
    """Coalesce concurrent async calls for the same key onto one shared task, so N
    callers trigger a single execution. The in-flight entry is dropped once the task
    settles — no result caching, so pair it with a cache when you need one."""

    def __init__(self) -> None:
        self._inflight: dict[K, asyncio.Task[V]] = {}

    async def run(self, key: K, factory: Callable[[], Coroutine[Any, Any, V]]) -> V:
        pending = self._inflight.get(key)
        if pending is not None:
            return await asyncio.shield(pending)
        task = asyncio.create_task(factory())
        self._inflight[key] = task
        try:
            return await task
        finally:
            self._inflight.pop(key, None)


def coalesce_future[V](cache: dict[str, asyncio.Future[V]], key: str, factory: Callable[[], Awaitable[V]]) -> asyncio.Future[V]:
    """Memoize an in-flight async call in a caller-owned dict (e.g. a request-scoped
    scene cache): the first call for a key schedules the task and stores its future;
    later calls return the same future. The result is kept for the dict's lifetime."""
    if key not in cache:
        cache[key] = asyncio.ensure_future(factory())
    return cache[key]
