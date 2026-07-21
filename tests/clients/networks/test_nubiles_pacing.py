from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import pytest

from app.clients.base import ActorResult, SceneDetail
from app.clients.networks import nubiles
from app.clients.networks.nubiles import _MAX_BACKOFF, _PACE_JITTER, _PACE_SECONDS, NubilesClient, _jittered, _retry_after_seconds


class _Resp:
    def __init__(self, retry_after: str | None) -> None:
        self.headers = {'retry-after': retry_after} if retry_after is not None else {}


def test_retry_after_numeric() -> None:
    assert _retry_after_seconds(_Resp('30')) == 30.0


def test_retry_after_absent() -> None:
    assert _retry_after_seconds(_Resp(None)) is None
    assert _retry_after_seconds(_Resp('   ')) is None


def test_retry_after_garbage() -> None:
    assert _retry_after_seconds(_Resp('soon')) is None


def test_retry_after_capped() -> None:
    assert _retry_after_seconds(_Resp('99999')) == _MAX_BACKOFF


def test_retry_after_http_date() -> None:
    when = datetime.now(UTC) + timedelta(seconds=45)
    secs = _retry_after_seconds(_Resp(format_datetime(when, usegmt=True)))
    assert secs is not None and 30 < secs <= 45


def test_retry_after_past_date_is_zero() -> None:
    when = datetime.now(UTC) - timedelta(seconds=60)
    assert _retry_after_seconds(_Resp(format_datetime(when, usegmt=True))) == 0.0


def test_jittered_within_range() -> None:
    for _ in range(100):
        v = _jittered(_PACE_SECONDS)
        assert _PACE_SECONDS <= v <= _PACE_SECONDS + _PACE_JITTER


async def test_warm_images_fetches_all_art_and_swallows_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def fake_fetch(url: str, referers: object = None, cookies: object = None, pinned: bool = False) -> object:
        calls.append(url)
        if 'bad' in url:
            raise ValueError('boom')
        return object()

    monkeypatch.setattr(nubiles, 'fetch_image', fake_fetch)
    client = NubilesClient()
    detail = SceneDetail(
        art=['https://images.momswapped.com/1.jpg', 'https://images.momswapped.com/bad.jpg', 'https://images.momswapped.com/2.jpg'],
        art_referer='https://momswapped.com/video/watch/1',
        art_cookie='pow=1',
        actors=[ActorResult(name='X')],
    )
    await client._warm_images(detail)
    assert set(calls) == set(detail.art)


async def test_warm_images_bounds_concurrency(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    active = 0
    peak = 0

    async def fake_fetch(url: str, referers: object = None, cookies: object = None, pinned: bool = False) -> object:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return object()

    monkeypatch.setattr(nubiles, 'fetch_image', fake_fetch)
    detail = SceneDetail(art=[f'https://images.nubiles-porn.com/{i}.jpg' for i in range(60)])
    await NubilesClient()._warm_images(detail)
    assert peak <= nubiles._IMAGE_CONCURRENCY


async def test_scene_window_cap_rests_after_four(monkeypatch: pytest.MonkeyPatch) -> None:
    import time as _t

    sleeps: list[float] = []

    async def fake_sleep(s: float) -> None:
        sleeps.append(s)

    monkeypatch.setattr(nubiles.asyncio, 'sleep', fake_sleep)
    client = NubilesClient()
    now = _t.monotonic()
    client._scene_starts.extend([now - 30, now - 20, now - 10, now - 5])
    await client._respect_scene_window()
    assert len(sleeps) == 1
    assert 560 < sleeps[0] <= nubiles._SCENE_WINDOW


async def test_scene_window_under_cap_and_stale_pruning(monkeypatch: pytest.MonkeyPatch) -> None:
    import time as _t

    async def fail_sleep(s: float) -> None:
        raise AssertionError('must not rest under the cap')

    monkeypatch.setattr(nubiles.asyncio, 'sleep', fail_sleep)
    client = NubilesClient()
    now = _t.monotonic()
    client._scene_starts.extend([now - 700, now - 650, now - 30, now - 20, now - 10])
    await client._respect_scene_window()
    assert len(client._scene_starts) == 4


async def test_warm_images_noop_without_art(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    async def fake_fetch(*_a: object, **_k: object) -> object:
        nonlocal called
        called = True
        return object()

    monkeypatch.setattr(nubiles, 'fetch_image', fake_fetch)
    await NubilesClient()._warm_images(SceneDetail())
    assert called is False
