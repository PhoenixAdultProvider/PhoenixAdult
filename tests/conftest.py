from __future__ import annotations

import os
import socket
import tempfile
from collections.abc import Iterator
from pathlib import Path
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
    """Fail fast on real network access: guards getaddrinfo (the choke point for every asyncio connect
    path, incl. the Windows Proactor loop) plus socket.connect; opt out with @pytest.mark.allow_network."""
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
def _state_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Every test gets its own state.db so nothing leaks into the repo-local default."""
    from phoenixadult.utils import db

    monkeypatch.setenv('STATE_DB_PATH', str(tmp_path / 'state.db'))
    yield
    db.close()


@pytest.fixture(autouse=True)
def _offline_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the anti-bot bypass chain offline (bypass_get escapes respx): pin BYPASS_ORDER to the HTTP
    backends and leave them unconfigured so http_bypass() returns None; bypass tests override this."""
    monkeypatch.setenv('BYPASS_ORDER', 'FlareSolverr,ReqBin')
    monkeypatch.delenv('FLARESOLVERR_URL', raising=False)
    monkeypatch.delenv('REQBIN_ENABLE', raising=False)
    from phoenixadult.utils.http.impersonate import impersonate_backend

    monkeypatch.setattr(impersonate_backend, 'is_available', lambda: False)


@pytest.fixture
def no_web_search() -> object:
    """A stand-in for a client module's imported web_search that finds nothing."""

    async def _none(*_args: object, **_kwargs: object) -> list[str]:
        return []

    return _none
