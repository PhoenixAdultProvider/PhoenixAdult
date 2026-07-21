from __future__ import annotations

import asyncio
import random
import time
import weakref
from collections import deque
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from app.config.env import env
from app.utils.logging.logger import logger

PLEX_REQUEST_BUDGET = 85.0

_GAP_JITTER_MIN = 10.0
_GAP_JITTER_MAX = 75.0
_SCENE_WINDOW = 600.0
_SCENE_WINDOW_MAX = 4
_SYNC_WAIT_BUDGET = 10.0

_PACERS: weakref.WeakSet[ScenePacer] = weakref.WeakSet()


def pacer_states() -> list[dict[str, object]]:
    """Live pacer state for the /queue UI, one row per registered pacer."""
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
            }
        )
    return out


class PacingDeferredError(Exception):
    """Raised instead of holding a Plex-facing request through a long pacing wait."""

    def __init__(self, wait_seconds: float) -> None:
        super().__init__(f'pacing requires waiting ~{wait_seconds:.0f}s')
        self.wait_seconds = wait_seconds


class ScenePacer:
    """Ban-avoidance pacing: jittered request spacing, one shared gap track for
    searches+scenes, a scenes-per-window cap, and Plex-budget deferral."""

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
        _PACERS.add(self)

    def jitter(self, base: float) -> float:
        """`base` seconds plus up to pace_jitter of randomness."""
        return base + random.uniform(0.0, self.pace_jitter)

    async def pace(self, label: str = 'request') -> None:
        """Per-request spacing: ~pace_seconds apart with jitter, logged under the tag."""
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
        """Wait before the next unit of work: the gap remainder, and for scenes also
        the window rest (the gap sleep ages the window, so max is exact)."""
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
        """One shared track: a search or scene consumes a turn and re-arms the gap;
        sync requests defer past _SYNC_WAIT_BUDGET, background work sleeps off-lock."""
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
