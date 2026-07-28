from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable


class SingleFlight[K, V]:
    def __init__(self, *, serve_stale: bool = True) -> None:
        self._serve_stale = serve_stale
        self._cache: dict[K, tuple[V, float]] = {}
        self._locks: dict[K, asyncio.Lock] = {}

    async def get(self, key: K, factory: Callable[[], Awaitable[tuple[V, float] | None]]) -> V | None:
        hit = self._cache.get(key)
        if hit and hit[1] > time.time():
            return hit[0]
        async with self._locks.setdefault(key, asyncio.Lock()):
            hit = self._cache.get(key)
            if hit and hit[1] > time.time():
                return hit[0]
            produced = await factory()
            if produced is None:
                return hit[0] if hit and self._serve_stale else None
            self._cache[key] = produced
            return produced[0]

    def clear(self) -> None:
        self._cache.clear()
        self._locks.clear()
