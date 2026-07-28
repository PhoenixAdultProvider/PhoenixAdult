from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any


class Coalescer[K, V]:
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
    if key not in cache:
        cache[key] = asyncio.ensure_future(factory())
    return cache[key]
