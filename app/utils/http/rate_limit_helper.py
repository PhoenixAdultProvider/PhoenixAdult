from __future__ import annotations

import asyncio
import random
import time
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.config.env import env
from app.utils.logging.logger import logger

PLEX_REQUEST_BUDGET = 85.0

_GAP_JITTER_MIN = 60.0
_GAP_JITTER_MAX = 240.0
_SCENE_WINDOW = 600.0
_SCENE_WINDOW_MAX = 4
_SYNC_WAIT_BUDGET = 10.0


class PacingDeferredError(Exception):
    """A client refused to hold a Plex-facing request through a long pacing wait (Plex
    kills provider requests at ~90s); the service queues a background scrape instead."""

    def __init__(self, wait_seconds: float) -> None:
        super().__init__(f'pacing requires waiting ~{wait_seconds:.0f}s')
        self.wait_seconds = wait_seconds


class ScenePacer:
    """Ban-avoidance pacing shared by rate-limited clients: jittered per-request
    spacing, a SCENE_GAP + 1-4 minute jittered between-scenes gap, a hard
    scenes-per-window cap, and Plex-budget deferral for synchronous requests."""

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

    def jitter(self, base: float) -> float:
        """`base` seconds plus up to pace_jitter of randomness, never machine-perfect."""
        return base + random.uniform(0.0, self.pace_jitter)

    async def pace(self, label: str = 'request') -> None:
        """Per-request spacing: every call waits its turn ~pace_seconds apart with
        jitter, and logs under the pacer tag so paced traffic is greppable."""
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

    def pending_wait(self) -> float:
        """Seconds a new scene must wait before scraping: the gap remainder or the
        window rest, whichever dominates (the gap sleep ages the window)."""
        now = time.monotonic()
        gap = max(0.0, self._gap_until - now)
        starts = [t for t in self._scene_starts if now - t <= _SCENE_WINDOW]
        rest = _SCENE_WINDOW - (now - starts[0]) if len(starts) >= _SCENE_WINDOW_MAX else 0.0
        return max(gap, rest)

    def _note_scene_start(self) -> None:
        now = time.monotonic()
        while self._scene_starts and now - self._scene_starts[0] > _SCENE_WINDOW:
            self._scene_starts.popleft()
        self._scene_starts.append(now)

    @asynccontextmanager
    async def scene(self, allow_slow: bool) -> AsyncIterator[None]:
        """One scene at a time: waits out (or defers) the gap/window, serializes on
        scene_lock, and schedules the next gap on exit. Plex-facing requests never
        sleep past _SYNC_WAIT_BUDGET — they raise PacingDeferredError instead;
        background scrapes (allow_slow) sleep the long wait OUTSIDE the lock so
        searches sharing it aren't starved."""
        wait = self.pending_wait()
        if not allow_slow and wait > _SYNC_WAIT_BUDGET:
            raise PacingDeferredError(wait)
        if allow_slow and wait > 0:
            logger.info(self.tag, f'background scrape waiting {wait:.0f}s (gap/window)')
            await asyncio.sleep(wait)
        async with self.scene_lock:
            wait = self.pending_wait()
            if not allow_slow and wait > _SYNC_WAIT_BUDGET:
                raise PacingDeferredError(wait)
            if wait > 0:
                logger.info(self.tag, f'between-scenes cooldown {wait:.1f}s')
                await asyncio.sleep(wait)
            self._note_scene_start()
            try:
                yield
            finally:
                self._gap_until = time.monotonic() + env.scene_gap + random.uniform(_GAP_JITTER_MIN, _GAP_JITTER_MAX)
