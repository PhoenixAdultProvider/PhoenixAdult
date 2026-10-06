from __future__ import annotations

import asyncio

import httpx2
import pytest

from phoenixadult.utils.http import client as http_client
from phoenixadult.utils.http import connectivity, ssrf_guard
from tests.support import authed_client


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    probes: list[int] = []

    async def unreachable() -> bool:
        probes.append(1)
        return False

    monkeypatch.setattr(connectivity, '_probe_once', unreachable)
    return probes


def _fail_lookups(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    lookups: list[str] = []

    async def no_dns(self: object, host: str, *args: object, **kwargs: object) -> list[object]:
        lookups.append(host)
        raise OSError('Temporary failure in name resolution')

    monkeypatch.setattr(asyncio.BaseEventLoop, 'getaddrinfo', no_dns)
    return lookups


async def test_a_failed_lookup_marks_the_network_down_and_later_lookups_fail_fast(monkeypatch: pytest.MonkeyPatch, offline: list[int]) -> None:
    lookups = _fail_lookups(monkeypatch)
    with pytest.raises(ValueError, match='cannot resolve host'):
        await ssrf_guard.assert_fetchable_url('https://a.example.com/x.jpg')
    assert connectivity.network_down()
    for _ in range(20):
        with pytest.raises(ValueError, match='cannot resolve host'):
            await ssrf_guard.assert_fetchable_url('https://b.example.com/x.jpg')
    assert lookups == ['a.example.com'], 'once down, lookups must not queue behind a dead resolver'
    assert len(offline) == 1, 'the probe is shared and cached, not run per request'


async def test_the_network_recovers_once_the_probe_succeeds(monkeypatch: pytest.MonkeyPatch, offline: list[int]) -> None:
    assert not await connectivity.internet_reachable()
    assert connectivity.network_down()

    async def reachable() -> bool:
        return True

    monkeypatch.setattr(connectivity, '_probe_once', reachable)
    connectivity._probe.clear()
    assert await connectivity.network_usable()
    assert not connectivity.network_down()


async def test_scrapers_fail_fast_on_public_hosts_but_lan_hosts_still_go_out(monkeypatch: pytest.MonkeyPatch, offline: list[int]) -> None:
    await connectivity.internet_reachable()
    seen: list[str] = []

    async def sent(self: object, request: httpx2.Request) -> httpx2.Response:
        seen.append(request.url.host)
        return httpx2.Response(200)

    monkeypatch.setattr(httpx2.AsyncHTTPTransport, 'handle_async_request', sent)
    transport = http_client._WatchedTransport()
    with pytest.raises(httpx2.ConnectError, match='network is down'):
        await transport.handle_async_request(httpx2.Request('GET', 'https://www.example.com/'))
    response = await transport.handle_async_request(httpx2.Request('GET', 'http://mipha.local:8191/v1'))
    assert response.status_code == 200 and seen == ['mipha.local']


def test_the_image_proxy_answers_503_without_resolving(monkeypatch: pytest.MonkeyPatch, offline: list[int]) -> None:
    lookups = _fail_lookups(monkeypatch)
    asyncio.run(connectivity.internet_reachable())
    response = authed_client().get('/images/proxy', params={'url': 'https://cdn.example.com/a.jpg'})
    assert response.status_code == 503
    assert lookups == []


def test_pages_show_the_banner_and_the_poll_endpoint_reports_it(offline: list[int]) -> None:
    client = authed_client()
    assert 'id="netBanner" role="status" hidden' in client.get('/queue').text
    assert client.get('/api/network').json() == {'down': False}
    asyncio.run(connectivity.internet_reachable())
    assert client.get('/api/network').json() == {'down': True}
    assert 'id="netBanner" role="status">' in client.get('/queue').text
