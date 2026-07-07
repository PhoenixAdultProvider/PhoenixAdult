from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any


class MtimeCachedJson[T]:
    """A JSON file parsed into T and reparsed whenever the file's mtime changes, so
    edits apply without a restart. The stat is rate-limited (get() can run several
    times per scene); the reparse is guarded by a lock and double-checked."""

    def __init__(self, path: Path, build: Callable[[Any], T], *, stat_interval: float = 5.0) -> None:
        self._path = path
        self._build = build
        self._stat_interval = stat_interval
        self._cache: tuple[float, T] | None = None
        self._stat_checked_at = 0.0
        self._lock = threading.Lock()

    def get(self) -> T:
        now = time.monotonic()
        if self._cache is not None and now - self._stat_checked_at < self._stat_interval:
            return self._cache[1]
        self._stat_checked_at = now
        try:
            mtime = self._path.stat().st_mtime
        except OSError:
            mtime = 0.0
        if self._cache is None or self._cache[0] != mtime:
            with self._lock:
                if self._cache is None or self._cache[0] != mtime:
                    self._cache = (mtime, self._build(json.loads(self._path.read_text(encoding='utf-8'))))
        return self._cache[1]
