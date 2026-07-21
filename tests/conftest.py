from __future__ import annotations

import os
import socket
import tempfile
from typing import Any

os.environ['LOG_DIR'] = os.path.join(tempfile.gettempdir(), 'phoenixadult-pytest-logs')

import pytest  # noqa: E402
import pytest_httpx2  # noqa: E402, F401  — registers the "httpcore2" respx mocker
import respx.mocks  # noqa: E402

respx.mocks.DEFAULT_MOCKER = 'httpcore2'

_LOCAL_HOSTS = ('localhost', '::1', '0.0.0.0', '::')


def _is_local(host: object) -> bool:
    if isinstance(host, bytes):
        host = host.decode('ascii', 'replace')
    return isinstance(host, str) and (host in _LOCAL_HOSTS or host.startswith('127.'))


@pytest.fixture(autouse=True)
def _no_live_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail fast on any real network access, so an env leak (e.g. a local .env enabling
    an enrichment) surfaces as an explicit error instead of a slow live call. Mocked
    HTTP (respx) never reaches the socket layer. Guards getaddrinfo — the choke point
    for every asyncio connect path, including the Windows Proactor loop which bypasses
    socket.connect — plus socket.connect itself. Opt out per-test with
    @pytest.mark.allow_network."""
    if request.node.get_closest_marker('allow_network'):
        return
    real_gai = socket.getaddrinfo
    real_connect = socket.socket.connect

    def guarded_gai(host: Any, port: Any, *args: Any, **kwargs: Any) -> Any:
        if _is_local(host):
            return real_gai(host, port, *args, **kwargs)
        raise RuntimeError(f'live network blocked in tests: getaddrinfo({host!r}) — mock it or mark the test @pytest.mark.allow_network')

    def guarded_connect(sock: socket.socket, address: Any) -> Any:
        """UDP connect stays allowed: it sends nothing (config's local-IP probe relies on it)."""
        host = address[0] if isinstance(address, tuple) and address else address
        if sock.type != socket.SOCK_STREAM or sock.family not in (socket.AF_INET, socket.AF_INET6) or _is_local(host):
            return real_connect(sock, address)
        raise RuntimeError(f'live network blocked in tests: connect({address!r}) — mock it or mark the test @pytest.mark.allow_network')

    monkeypatch.setattr(socket, 'getaddrinfo', guarded_gai)
    monkeypatch.setattr(socket.socket, 'connect', guarded_connect)


@pytest.fixture(autouse=True)
def _offline_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the anti-bot bypass chain offline by default.

    bypass_get() escapes respx (Impersonate/curl_cffi, Playwright aren't httpx), so
    a source/scraper that falls through to it would make a real network call. Pin the
    order to the HTTP backends and leave them unconfigured → every backend is
    unavailable → http_bypass() returns None. Tests that exercise bypass set their own
    BYPASS_ORDER + backend config, which overrides this.
    """
    monkeypatch.setenv('BYPASS_ORDER', 'FlareSolverr,ReqBin')
    monkeypatch.delenv('FLARESOLVERR_URL', raising=False)
    monkeypatch.delenv('REQBIN_ENABLE', raising=False)
    from app.utils.http.impersonate import impersonate_backend

    monkeypatch.setattr(impersonate_backend, 'is_available', lambda: False)


@pytest.fixture
def no_web_search() -> object:
    """A stand-in for a client module's imported web_search that finds nothing."""

    async def _none(*_args: object, **_kwargs: object) -> list[str]:
        return []

    return _none
