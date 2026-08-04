from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from cachetools import TTLCache

_FREE_ATTEMPTS = 5
_MAX_BACKOFF = 300.0
_IDLE_PRUNE_SECONDS = 3600.0


@dataclass
class _Bucket:
    failures: int = 0
    last_failure: float = field(default=0.0)


_buckets: TTLCache[tuple[str, str], _Bucket] = TTLCache(maxsize=4096, ttl=_IDLE_PRUNE_SECONDS)
_lock = threading.Lock()


def retry_after(scope: str, key: str) -> float:
    now = time.time()
    with _lock:
        bucket = _buckets.get((scope, key))
        if bucket is None or bucket.failures <= _FREE_ATTEMPTS:
            return 0.0
        wait = min(_MAX_BACKOFF, 2.0 ** (bucket.failures - _FREE_ATTEMPTS))
        remaining = bucket.last_failure + wait - now
        return max(0.0, remaining)


def record_failure(scope: str, key: str) -> None:
    now = time.time()
    with _lock:
        bucket = _buckets.get((scope, key)) or _Bucket()
        bucket.failures += 1
        bucket.last_failure = now
        _buckets[(scope, key)] = bucket


def record_success(scope: str, key: str) -> None:
    with _lock:
        _buckets.pop((scope, key), None)
