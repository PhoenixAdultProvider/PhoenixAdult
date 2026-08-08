from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import pytest

from phoenixadult.clients.base import ActorResult, SceneDetail
from phoenixadult.clients.networks import nubiles
from phoenixadult.clients.networks.nubiles import _MAX_BACKOFF, _PACE_JITTER, _PACE_SECONDS, NubilesClient, _jittered, _retry_after_seconds


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


def test_pending_wait_window_cap_after_max_scenes() -> None:
    import time as _t

    from phoenixadult.utils.http import rate_limit_helper as rlh

    client = NubilesClient()
    now = _t.monotonic()
    client.pacer._scene_starts.extend([now - 80 + i * 10 for i in range(rlh._SCENE_WINDOW_MAX)])
    assert 500 < client.pacer.pending_wait() <= rlh._SCENE_WINDOW


def test_pending_wait_ignores_stale_starts_and_uses_gap() -> None:
    import time as _t

    client = NubilesClient()
    now = _t.monotonic()
    client.pacer._scene_starts.extend([now - 700, now - 650, now - 30])
    assert client.pacer.pending_wait() == 0.0
    client.pacer._gap_until = now + 120
    assert 115 < client.pacer.pending_wait() <= 120


async def test_sync_scene_defers_instead_of_sleeping() -> None:
    import time as _t

    from phoenixadult.clients.base import PacingDeferredError
    from phoenixadult.registry import find_site

    site = find_site('Nubile Films')
    assert site is not None
    client = NubilesClient()
    client.pacer._gap_until = _t.monotonic() + 300
    with pytest.raises(PacingDeferredError) as err:
        await client.fetch_scene_detail('1|2020-01-01', site)
    assert err.value.wait_seconds > 290


async def test_search_shares_the_gap_track(monkeypatch: pytest.MonkeyPatch) -> None:

    from phoenixadult.clients.base import PacingDeferredError, SearchContext
    from phoenixadult.registry import find_site
    from phoenixadult.utils.http import rate_limit_helper as rlh

    site = find_site('Nubile Films')
    assert site is not None
    monkeypatch.setenv('SCENE_GAP', '120')
    monkeypatch.setattr(rlh, '_GAP_JITTER_MIN', 0.0)
    monkeypatch.setattr(rlh, '_GAP_JITTER_MAX', 0.0)
    client = NubilesClient()

    async def _noop_search(results: object, search_data: object) -> None:
        return None

    monkeypatch.setattr(client, '_search', _noop_search)
    ctx = SearchContext(title='x', encoded='x', search_site=site.name, site_info=site)
    await client.search([], ctx)
    assert 110 < client.pacer.pending_wait(include_window=False) <= 120

    with pytest.raises(PacingDeferredError):
        await client.fetch_scene_detail('1|2020-01-01', site)
    with pytest.raises(PacingDeferredError):
        await client.search([], ctx)


async def test_warm_images_noop_without_art(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    async def fake_fetch(*_a: object, **_k: object) -> object:
        nonlocal called
        called = True
        return object()

    monkeypatch.setattr(nubiles, 'fetch_image', fake_fetch)
    await NubilesClient()._warm_images(SceneDetail())
    assert called is False


class _Site:
    base_url = 'https://nubilefilms.com'
    search_path = '/video/search'


def _quiet_client(monkeypatch: pytest.MonkeyPatch) -> NubilesClient:
    client = NubilesClient()

    async def no_pace(label: str = 'request') -> None:
        return None

    async def no_cookies(site: object) -> str:
        return ''

    async def no_sleep(_secs: float) -> None:
        return None

    monkeypatch.setattr(client.pacer, 'pace', no_pace)
    monkeypatch.setattr(client, '_cookie_header_for', no_cookies)
    monkeypatch.setattr(nubiles.asyncio, 'sleep', no_sleep)
    return client


async def test_a_transport_blip_is_retried_not_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _quiet_client(monkeypatch)
    calls = {'n': 0}

    class _OkResp:
        status_code = 200
        text = '<html>ok</html>'

    async def flaky(url: str, **kwargs: object) -> _OkResp:
        calls['n'] += 1
        if calls['n'] == 1:
            raise ConnectionError('reset')
        return _OkResp()

    monkeypatch.setattr(client.http, 'get', flaky)
    page = await client._get('https://nubilefilms.com/x', _Site(), None, 'test')
    assert page is not None and calls['n'] == 2
    assert client.pacer._ban_until == 0.0


async def test_persistent_refusal_with_internet_up_pauses_the_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _quiet_client(monkeypatch)

    async def refused(url: str, **kwargs: object) -> object:
        raise ConnectionError('refused')

    async def online() -> bool:
        return True

    banned = {'called': False}
    monkeypatch.setattr(client.http, 'get', refused)
    monkeypatch.setattr(nubiles, 'internet_reachable', online)
    monkeypatch.setattr(client.pacer, 'flag_ban', lambda *a, **k: banned.update(called=True))
    assert await client._get('https://nubilefilms.com/x', _Site(), None, 'test') is None
    assert banned['called'], 'a connection refused with the internet reachable is a network-level ban'


async def test_persistent_refusal_while_offline_blames_nobody(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _quiet_client(monkeypatch)

    async def refused(url: str, **kwargs: object) -> object:
        raise ConnectionError('refused')

    async def offline() -> bool:
        return False

    banned = {'called': False}
    monkeypatch.setattr(client.http, 'get', refused)
    monkeypatch.setattr(nubiles, 'internet_reachable', offline)
    monkeypatch.setattr(client.pacer, 'flag_ban', lambda *a, **k: banned.update(called=True))
    assert await client._get('https://nubilefilms.com/x', _Site(), None, 'test') is None
    assert not banned['called'], 'a local outage must not pause the queue for 15 minutes'


async def test_a_successful_request_clears_an_active_ban(monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.services import scrape_queue

    client = _quiet_client(monkeypatch)
    client.pacer.flag_ban()
    assert scrape_queue.paused_for() > 0
    revision_before = scrape_queue.snapshot()['revision']

    class _OkResp:
        status_code = 200
        text = '<html>ok</html>'

    async def ok(url: str, **kwargs: object) -> _OkResp:
        return _OkResp()

    monkeypatch.setattr(client.http, 'get', ok)
    assert await client._get('https://nubilefilms.com/x', _Site(), None, 'test') is not None
    assert client.pacer._ban_until == 0.0, 'the ban must not outlive proof the site is answering'
    assert scrape_queue.paused_for() == 0, 'the queue pause caused by the ban lifts with it'
    assert scrape_queue.snapshot()['revision'] > revision_before, 'the UI longpoll must be woken to repaint the pacer tile'


async def test_clearing_without_a_ban_does_not_wake_the_ui(monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.services import scrape_queue

    client = _quiet_client(monkeypatch)
    revision_before = scrape_queue.snapshot()['revision']
    client.pacer.clear_ban()
    assert scrape_queue.snapshot()['revision'] == revision_before, 'no ban means nothing changed; longpolls stay asleep'


async def test_a_manual_pause_survives_another_sites_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.services import scrape_queue

    client = _quiet_client(monkeypatch)
    client.pacer.flag_ban()
    scrape_queue.pause('SomeOther ban detected', 500)
    client.pacer.clear_ban()
    assert scrape_queue.paused_for() > 0, "clearing this site's ban must not resume a pause owned by another reason"
