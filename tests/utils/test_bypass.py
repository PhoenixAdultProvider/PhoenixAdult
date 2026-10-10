from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import httpx
import httpx2
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


class _StubSession:
    fail_with: str = ''
    calls = 0

    async def __aenter__(self) -> _StubSession:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def post(self, url: str, **_kw: object) -> SimpleNamespace:
        type(self).calls += 1
        if type(self).fail_with and type(self).calls == 1:
            raise RuntimeError(type(self).fail_with)
        if type(self).fail_with and 'resolve host' in type(self).fail_with:
            raise RuntimeError(type(self).fail_with)
        return SimpleNamespace(status_code=200, text='<html>hit</html>', headers={}, cookies={}, url=url)

    async def get(self, url: str, **kw: object) -> SimpleNamespace:
        return await self.post(url, **kw)


def _stub_curl_cffi(monkeypatch: pytest.MonkeyPatch, fail_with: str) -> type[_StubSession]:
    _StubSession.calls = 0
    _StubSession.fail_with = fail_with
    module = ModuleType('curl_cffi.requests')
    module.AsyncSession = _StubSession  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, 'curl_cffi', ModuleType('curl_cffi'))
    monkeypatch.setitem(sys.modules, 'curl_cffi.requests', module)
    return _StubSession


async def test_a_reset_stream_is_retried_once_rather_than_failing_the_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.utils.http.impersonate import impersonate_backend

    monkeypatch.delattr(impersonate_backend, 'request')

    session = _stub_curl_cffi(monkeypatch, 'Failed to perform, curl: (92) HTTP/2 stream 1 reset by server (error 0x2 INTERNAL_ERROR).')
    monkeypatch.setattr('phoenixadult.utils.http.impersonate._RETRY_PAUSE', 0)
    got = await impersonate_backend.request(BypassRequest(url='https://www.scoreland.com/search-es', method='POST', body='keywords=x'))
    assert got is not None and got.status == 200
    assert session.calls == 2, 'the first attempt must be retried, not abandoned'


async def test_a_failure_that_is_not_transient_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.utils.http.impersonate import impersonate_backend

    monkeypatch.delattr(impersonate_backend, 'request')

    session = _stub_curl_cffi(monkeypatch, 'Failed to perform, curl: (6) Could not resolve host')
    assert await impersonate_backend.request(BypassRequest(url='https://nope.example/x', method='POST', body='')) is None
    assert session.calls == 1, 'a dead host must not be tried twice'


@respx.mock
async def test_an_unreachable_solver_names_the_endpoint_it_could_not_reach(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    import logging

    from phoenixadult.utils.http.flaresolverr import flare_solverr_backend

    monkeypatch.setenv('FLARESOLVERR_URL', 'http://mipha.local:8191')
    respx.post('http://mipha.local:8191/v1').mock(side_effect=httpx2.ConnectError('All connection attempts failed'))
    with caplog.at_level(logging.WARNING):
        assert await flare_solverr_backend.request(BypassRequest(url='https://example.com/x', method='GET')) is None
    assert 'http://mipha.local:8191/v1' in caplog.text, 'the warning must name the endpoint, not just the transport error'
    assert 'FLARESOLVERR_URL' in caplog.text


@respx.mock
async def test_the_solver_receives_the_post_body_and_cookies_and_its_solution_is_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    from phoenixadult.utils.http.flaresolverr import flare_solverr_backend

    monkeypatch.setenv('FLARESOLVERR_URL', 'http://solver.test:8191/')
    solution = {'status': 200, 'response': '<html>ok</html>', 'cookies': [{'name': 'cf', 'value': '1'}], 'userAgent': 'UA', 'url': 'https://example.com/y'}
    route = respx.post('http://solver.test:8191/v1').mock(return_value=httpx.Response(200, json={'status': 'ok', 'solution': solution}))
    got = await flare_solverr_backend.request(BypassRequest(url='https://example.com/x', method='POST', body='a=1', cookies={'s': '2'}, timeout_ms=5000))
    sent = json.loads(route.calls[0].request.content)
    assert sent == {
        'cmd': 'request.post',
        'url': 'https://example.com/x',
        'maxTimeout': 5000,
        'headers': {},
        'cookies': [{'name': 's', 'value': '2'}],
        'postData': 'a=1',
    }
    assert got is not None and (got.status, got.body, got.cookies, got.final_url, got.user_agent) == (
        200,
        '<html>ok</html>',
        {'cf': '1'},
        'https://example.com/y',
        'UA',
    )


@respx.mock
async def test_a_solver_error_is_no_response(monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.utils.http.flaresolverr import flare_solverr_backend

    monkeypatch.setenv('FLARESOLVERR_URL', 'http://solver.test:8191')
    respx.post('http://solver.test:8191/v1').mock(return_value=httpx.Response(200, json={'status': 'error', 'message': 'challenge failed'}))
    assert await flare_solverr_backend.request(BypassRequest(url='https://example.com/x', method='GET')) is None
