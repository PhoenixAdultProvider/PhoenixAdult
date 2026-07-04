from __future__ import annotations

import httpx
import pytest
import respx

from app.utils.http import pinned_fetch, ssrf_guard
from app.utils.http.pinned_fetch import fetch_pinned

IP = '203.0.113.7'


@pytest.fixture(autouse=True)
def _no_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ('HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy'):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def _resolve_public(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_resolve(host: str) -> list[str]:
        return [IP]

    monkeypatch.setattr(ssrf_guard, '_resolve', fake_resolve)


@respx.mock
async def test_fetch_connects_to_pinned_ip_with_host_header(_resolve_public: None) -> None:
    seen: dict[str, str] = {}

    def responder(request: httpx.Request) -> httpx.Response:
        seen['host'] = request.headers.get('host', '')
        return httpx.Response(200, content=b'ok', headers={'Content-Type': 'image/jpeg'})

    respx.get(f'http://{IP}/img.jpg').mock(side_effect=responder)
    resp = await fetch_pinned('http://example.com/img.jpg')
    assert resp.status_code == 200
    assert seen['host'] == 'example.com'


@respx.mock
async def test_redirect_to_blocked_host_raises(_resolve_public: None) -> None:
    respx.get(f'http://{IP}/a').mock(return_value=httpx.Response(302, headers={'Location': 'http://internal.local/secret'}))
    with pytest.raises(ValueError, match='blocked host'):
        await fetch_pinned('http://example.com/a')


@respx.mock
async def test_redirect_to_public_host_is_repinned(_resolve_public: None) -> None:
    respx.get(f'http://{IP}/a').mock(return_value=httpx.Response(302, headers={'Location': 'http://other.example/b'}))

    def responder(request: httpx.Request) -> httpx.Response:
        assert request.headers.get('host') == 'other.example'
        return httpx.Response(200, content=b'ok', headers={'Content-Type': 'image/jpeg'})

    respx.get(f'http://{IP}/b').mock(side_effect=responder)
    resp = await fetch_pinned('http://example.com/a')
    assert resp.status_code == 200


async def test_private_resolution_never_fetches(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_resolve(host: str) -> list[str]:
        return ['10.0.0.5']

    monkeypatch.setattr(ssrf_guard, '_resolve', fake_resolve)
    with pytest.raises(ValueError, match='private address'):
        await fetch_pinned('http://example.com/a')


@respx.mock
async def test_redirect_loop_gives_up(_resolve_public: None) -> None:
    respx.get(f'http://{IP}/loop').mock(return_value=httpx.Response(302, headers={'Location': 'http://example.com/loop'}))
    with pytest.raises(ValueError, match='too many redirects'):
        await fetch_pinned('http://example.com/loop')


async def test_ip_literal_target_is_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match='blocked host'):
        await fetch_pinned('http://127.0.0.1/x')
    assert pinned_fetch._ip_netloc('2001:db8::1', 8443) == '[2001:db8::1]:8443'
