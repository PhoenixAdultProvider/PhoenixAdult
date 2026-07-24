from __future__ import annotations

import time

import pytest

from phoenixadult.utils.images import image_fetcher as fetcher
from phoenixadult.utils.images.image_fetcher import ImageEntry, _cache_get, _cache_put


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    fetcher._cache.clear()
    fetcher._cache_total_bytes = 0


def _entry(size: int, cached_at: float | None = None) -> ImageEntry:
    return ImageEntry(data=b'x' * size, content_type='image/jpeg', cached_at=cached_at or time.time(), width=1, height=1)


def test_put_get_roundtrip() -> None:
    e = _entry(10)
    _cache_put('u1', e)
    assert _cache_get('u1') is e
    assert fetcher._cache_total_bytes == 10


def test_expired_entry_dropped_on_get() -> None:
    _cache_put('u1', _entry(10, cached_at=time.time() - fetcher._CACHE_TTL - 1))
    assert _cache_get('u1') is None
    assert fetcher._cache_total_bytes == 0


def test_lru_eviction_respects_byte_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fetcher, '_CACHE_MAX_TOTAL_BYTES', 25)
    _cache_put('a', _entry(10))
    _cache_put('b', _entry(10))
    _cache_get('a')
    _cache_put('c', _entry(10))
    assert _cache_get('b') is None
    assert _cache_get('a') is not None
    assert _cache_get('c') is not None
    assert fetcher._cache_total_bytes == 20


def test_replacing_entry_does_not_leak_bytes() -> None:
    _cache_put('a', _entry(10))
    _cache_put('a', _entry(4))
    assert fetcher._cache_total_bytes == 4
