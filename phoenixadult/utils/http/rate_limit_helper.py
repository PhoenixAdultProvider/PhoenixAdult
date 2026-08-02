from __future__ import annotations

import asyncio
import random
import time
import weakref
from collections import deque
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from contextvars import ContextVar

from phoenixadult.config.env import env
from phoenixadult.utils.logging.logger import logger

PLEX_REQUEST_BUDGET = 85.0

_GAP_JITTER_MIN = 10.0
_GAP_JITTER_MAX = 45.0
_SCENE_WINDOW = 600.0
_SCENE_WINDOW_MAX = 8
_SYNC_WAIT_BUDGET = 10.0

_PACERS: weakref.WeakSet[ScenePacer] = weakref.WeakSet()


def pacer_states() -> list[dict[str, object]]:
    out = []
    for p in sorted(_PACERS, key=lambda p: p.tag):
        now = time.monotonic()
        in_window = len([t for t in p._scene_starts if now - t <= _SCENE_WINDOW])
        out.append(
            {
                'tag': p.tag,
                'wait': round(p.pending_wait(), 1),
                'gap': round(max(0.0, p._gap_until - now), 1),
                'window_used': in_window,
                'window_max': _SCENE_WINDOW_MAX,
                'busy': p.scene_lock.locked(),
                'ban': round(max(0.0, p._ban_until - now), 1),
            }
        )
    return out


class PacingDeferredError(Exception):
    def __init__(self, wait_seconds: float) -> None:
        super().__init__(f'pacing requires waiting ~{wait_seconds:.0f}s')
        self.wait_seconds = wait_seconds


_FAST_SLOTS = 3
_fast_slot_held: ContextVar[bool] = ContextVar('fast_slot_held', default=False)


class FastGate:
    def __init__(self, slots: int = _FAST_SLOTS) -> None:
        self.slots = slots
        self._active = 0
        self._waiters: list[asyncio.Future[None]] = []
        self._loop_id: int | None = None

    def state(self) -> dict[str, int]:
        return {'busy': self._active, 'slots': self.slots, 'waiting': len(self._waiters)}

    def _ensure_loop(self) -> None:
        loop_id = id(asyncio.get_running_loop())
        if self._loop_id != loop_id:
            self._loop_id = loop_id
            self._active = 0
            self._waiters = []

    def _wake(self) -> None:
        for waiter in self._waiters:
            if not waiter.done():
                waiter.set_result(None)

    async def _acquire(self) -> None:
        while self._active >= self.slots:
            waiter: asyncio.Future[None] = asyncio.get_running_loop().create_future()
            self._waiters.append(waiter)
            try:
                await waiter
            finally:
                self._waiters.remove(waiter)
        self._active += 1

    @asynccontextmanager
    async def turn(self, allow_slow: bool) -> AsyncIterator[None]:
        self._ensure_loop()
        if _fast_slot_held.get():
            yield
            return
        if allow_slow:
            await self._acquire()
        else:
            try:
                await asyncio.wait_for(self._acquire(), _SYNC_WAIT_BUDGET)
            except TimeoutError:
                raise PacingDeferredError(_SYNC_WAIT_BUDGET * (len(self._waiters) + 1)) from None
        token = _fast_slot_held.set(True)
        try:
            yield
        finally:
            _fast_slot_held.reset(token)
            self._active -= 1
            self._wake()


FAST_GATE = FastGate()


class ScenePacer:
    def __init__(self, tag: str, *, pace_seconds: float = 7.0, pace_jitter: float = 3.0, cooldown_seconds: float = 7.0) -> None:
        self.tag = tag
        self.pace_seconds = pace_seconds
        self.pace_jitter = pace_jitter
        self.cooldown_seconds = cooldown_seconds
        self.scene_lock = asyncio.Lock()
        self._pace_lock = asyncio.Lock()
        self._last_fetch = 0.0
        self._gap_until = 0.0
        self._scene_starts: deque[float] = deque()
        self._ban_until = 0.0
        _PACERS.add(self)

    def flag_ban(self, seconds: float = 900.0) -> None:
        from phoenixadult.services import scrape_queue

        self._ban_until = time.monotonic() + seconds
        scrape_queue.pause(f'{self.tag} ban detected', seconds)

    def jitter(self, base: float) -> float:
        return base + random.uniform(0.0, self.pace_jitter)

    async def pace(self, label: str = 'request') -> None:
        async with self._pace_lock:
            wait = self.jitter(self.pace_seconds) - (time.monotonic() - self._last_fetch)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_fetch = time.monotonic()
        logger.info(self.tag, f'{label} (waited {max(0.0, wait):.1f}s)')

    async def cooldown(self, phase: str) -> None:
        delay = self.jitter(self.cooldown_seconds)
        logger.info(self.tag, f'{phase} cooldown {delay:.1f}s')
        await asyncio.sleep(delay)

    def pending_wait(self, *, include_window: bool = True) -> float:
        now = time.monotonic()
        gap = max(0.0, self._gap_until - now)
        if not include_window:
            return gap
        starts = [t for t in self._scene_starts if now - t <= _SCENE_WINDOW]
        rest = _SCENE_WINDOW - (now - starts[0]) if len(starts) >= _SCENE_WINDOW_MAX else 0.0
        return max(gap, rest)

    def _note_scene_start(self) -> None:
        now = time.monotonic()
        while self._scene_starts and now - self._scene_starts[0] > _SCENE_WINDOW:
            self._scene_starts.popleft()
        self._scene_starts.append(now)

    @asynccontextmanager
    async def _turn(self, allow_slow: bool, *, is_scene: bool) -> AsyncIterator[None]:
        kind = 'scene' if is_scene else 'search'
        wait = self.pending_wait(include_window=is_scene)
        if not allow_slow and wait > _SYNC_WAIT_BUDGET:
            raise PacingDeferredError(wait)
        if allow_slow and wait > 0:
            logger.info(self.tag, f'background {kind} waiting {wait:.0f}s (gap/window)')
            await asyncio.sleep(wait)
        async with self.scene_lock:
            wait = self.pending_wait(include_window=is_scene)
            if not allow_slow and wait > _SYNC_WAIT_BUDGET:
                raise PacingDeferredError(wait)
            if wait > 0:
                logger.info(self.tag, f'{kind} gap wait {wait:.1f}s')
                await asyncio.sleep(wait)
            if is_scene:
                self._note_scene_start()
            try:
                yield
            finally:
                self._gap_until = time.monotonic() + env.scene_gap + random.uniform(_GAP_JITTER_MIN, _GAP_JITTER_MAX)

    def scene(self, allow_slow: bool) -> AbstractAsyncContextManager[None]:
        return self._turn(allow_slow, is_scene=True)

    def search_gate(self, allow_slow: bool) -> AbstractAsyncContextManager[None]:
        return self._turn(allow_slow, is_scene=False)
