from __future__ import annotations

import time

import pytest
from cachetools import TTLCache

from phoenixadult.utils.images import image_fetcher as fetcher
from phoenixadult.utils.images.image_fetcher import ImageEntry, _cache_get, _cache_put


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    fetcher._cache.clear()


def _entry(size: int) -> ImageEntry:
    return ImageEntry(data=b'x' * size, content_type='image/jpeg', cached_at=time.time(), width=1, height=1)


def _swap_cache(monkeypatch: pytest.MonkeyPatch, maxsize: int, timer: object | None = None) -> TTLCache[str, ImageEntry]:
    opts: dict[str, object] = {'maxsize': maxsize, 'ttl': fetcher._CACHE_TTL, 'getsizeof': lambda e: len(e.data)}
    if timer is not None:
        opts['timer'] = timer
    cache: TTLCache[str, ImageEntry] = TTLCache(**opts)  # type: ignore[arg-type]
    monkeypatch.setattr(fetcher, '_cache', cache)
    return cache


def test_put_get_roundtrip() -> None:
    e = _entry(10)
    _cache_put('u1', e)
    assert _cache_get('u1') is e
    assert fetcher._cache.currsize == 10


def test_expired_entry_dropped_on_get(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [0.0]
    _swap_cache(monkeypatch, maxsize=1000, timer=lambda: now[0])
    _cache_put('u1', _entry(10))
    now[0] = fetcher._CACHE_TTL + 1
    assert _cache_get('u1') is None


def test_lru_eviction_respects_byte_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    cache = _swap_cache(monkeypatch, maxsize=25)
    _cache_put('a', _entry(10))
    _cache_put('b', _entry(10))
    _cache_get('a')
    _cache_put('c', _entry(10))
    assert _cache_get('b') is None
    assert _cache_get('a') is not None
    assert _cache_get('c') is not None
    assert cache.currsize == 20


def test_replacing_entry_does_not_leak_bytes() -> None:
    _cache_put('a', _entry(10))
    _cache_put('a', _entry(4))
    assert fetcher._cache.currsize == 4
