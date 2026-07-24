from __future__ import annotations

import httpx
import pytest
import respx

from phoenixadult.utils.http.bypass import bypass_get, http_bypass
from phoenixadult.utils.http.bypass_types import BypassRequest


def test_impersonate_registered_first() -> None:
    from phoenixadult.utils.http.bypass import ALL_BACKENDS
    from phoenixadult.utils.http.impersonate import impersonate_backend

    assert ALL_BACKENDS[0] is impersonate_backend
    assert impersonate_backend.name == 'Impersonate'


def test_configured_order_includes_impersonate(monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.utils.http.bypass import _configured_order

    monkeypatch.setenv('BYPASS_ORDER', 'Impersonate,FlareSolverr')
    assert [b.name for b in _configured_order()] == ['Impersonate', 'FlareSolverr']


async def test_all_unavailable_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('BYPASS_ORDER', 'FlareSolverr,ReqBin')
    monkeypatch.delenv('FLARESOLVERR_URL', raising=False)
    monkeypatch.delenv('REQBIN_ENABLE', raising=False)
    assert await bypass_get('https://example.com') is None


@respx.mock
async def test_flaresolverr_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('FLARESOLVERR_URL', 'http://localhost:8191')
    monkeypatch.setenv('BYPASS_ORDER', 'FlareSolverr')
    envelope = {
        'status': 'ok',
        'solution': {
            'url': 'https://example.com/final',
            'status': 200,
            'response': '<html>ok</html>',
            'headers': {'content-type': 'text/html'},
            'cookies': [{'name': 'cf', 'value': 'abc'}],
        },
    }
    respx.post('http://localhost:8191/v1').mock(return_value=httpx.Response(200, json=envelope))
    resp = await bypass_get('https://example.com')
    assert resp is not None
    assert resp.status == 200
    assert resp.body == '<html>ok</html>'
    assert resp.cookies == {'cf': 'abc'}
    assert resp.final_url == 'https://example.com/final'


@respx.mock
async def test_unsolved_challenge_body_not_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('FLARESOLVERR_URL', 'http://localhost:8191')
    monkeypatch.setenv('BYPASS_ORDER', 'FlareSolverr')
    envelope = {
        'status': 'ok',
        'solution': {
            'url': 'https://example.com/',
            'status': 200,
            'response': '<html><script>window.awsWafCookieDomainList=[]</script><div id="challenge-container"></div></html>',
            'headers': {},
            'cookies': [],
        },
    }
    respx.post('http://localhost:8191/v1').mock(return_value=httpx.Response(200, json=envelope))
    assert await http_bypass(BypassRequest(url='https://example.com')) is None


@respx.mock
async def test_flaresolverr_solver_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('FLARESOLVERR_URL', 'http://localhost:8191')
    monkeypatch.setenv('BYPASS_ORDER', 'FlareSolverr')
    respx.post('http://localhost:8191/v1').mock(return_value=httpx.Response(200, json={'status': 'error', 'message': 'nope'}))
    assert await http_bypass(BypassRequest(url='https://example.com')) is None
