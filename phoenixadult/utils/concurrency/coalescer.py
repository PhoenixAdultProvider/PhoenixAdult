from __future__ import annotations

import asyncio
import functools
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any


class Coalescer[K, V]:
    def __init__(self) -> None:
        self._inflight: dict[K, asyncio.Task[V]] = {}

    async def run(self, key: K, factory: Callable[[], Coroutine[Any, Any, V]]) -> V:
        task = self._inflight.get(key)
        if task is None:
            task = asyncio.create_task(factory())
            self._inflight[key] = task
            task.add_done_callback(functools.partial(self._settle, key))
        return await asyncio.shield(task)

    def _settle(self, key: K, task: asyncio.Task[V]) -> None:
        if self._inflight.get(key) is task:
            del self._inflight[key]
        if not task.cancelled():
            task.exception()


def coalesce_future[V](cache: dict[str, asyncio.Future[V]], key: str, factory: Callable[[], Awaitable[V]]) -> asyncio.Future[V]:
    if key not in cache:
        cache[key] = asyncio.ensure_future(factory())
    return cache[key]
