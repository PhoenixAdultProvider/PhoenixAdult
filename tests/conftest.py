from __future__ import annotations

import os
import shutil
import socket
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

os.environ['LOG_DIR'] = os.path.join(tempfile.gettempdir(), 'phoenixadult-pytest-logs')
os.environ['NODE_ENV'] = 'test'

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
    if request.node.get_closest_marker('allow_network'):
        return
    real_gai = socket.getaddrinfo
    real_connect = socket.socket.connect

    def guarded_gai(host: Any, port: Any, *args: Any, **kwargs: Any) -> Any:
        if _is_local(host):
            return real_gai(host, port, *args, **kwargs)
        raise RuntimeError(f'live network blocked in tests: getaddrinfo({host!r}) — mock it or mark the test @pytest.mark.allow_network')

    def guarded_connect(sock: socket.socket, address: Any) -> Any:
        host = address[0] if isinstance(address, tuple) and address else address
        if sock.type != socket.SOCK_STREAM or sock.family not in (socket.AF_INET, socket.AF_INET6) or _is_local(host):
            return real_connect(sock, address)
        raise RuntimeError(f'live network blocked in tests: connect({address!r}) — mock it or mark the test @pytest.mark.allow_network')

    monkeypatch.setattr(socket, 'getaddrinfo', guarded_gai)
    monkeypatch.setattr(socket.socket, 'connect', guarded_connect)


@pytest.fixture(scope='session', autouse=True)
def _cheap_password_hashing() -> None:
    from argon2 import PasswordHasher

    from phoenixadult.utils.auth import passwords

    passwords._hasher = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)


@pytest.fixture(scope='session')
def _migrated_schema(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    from phoenixadult.utils import db

    template = tmp_path_factory.mktemp('schema') / 'template.db'
    previous = os.environ.get('STATE_DB_PATH')
    os.environ['STATE_DB_PATH'] = str(template)
    try:
        db.connect()
    finally:
        db.close()
        if previous is None:
            os.environ.pop('STATE_DB_PATH', None)
        else:
            os.environ['STATE_DB_PATH'] = previous
    yield template


@pytest.fixture(autouse=True)
def _state_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, _migrated_schema: Path) -> Iterator[None]:
    from phoenixadult.utils import db

    target = tmp_path / 'state.db'
    shutil.copyfile(_migrated_schema, target)
    monkeypatch.setenv('STATE_DB_PATH', str(target))
    yield
    db.close()


@pytest.fixture(autouse=True)
def _isolated_local_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv('IMAGE_DIR', str(tmp_path / 'images'))
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path / 'cache'))


@pytest.fixture(autouse=True)
def _offline_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('BYPASS_ORDER', 'FlareSolverr,ReqBin')
    monkeypatch.delenv('FLARESOLVERR_URL', raising=False)
    monkeypatch.delenv('REQBIN_ENABLE', raising=False)
    from phoenixadult.utils.http.impersonate import impersonate_backend

    monkeypatch.setattr(impersonate_backend, 'is_available', lambda: False)


@pytest.fixture(autouse=True)
def _network_up(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    from phoenixadult.utils.http import connectivity

    async def reachable() -> bool:
        return True

    monkeypatch.setattr(connectivity, '_probe_once', reachable)
    connectivity.reset_network_state()
    yield
    connectivity.reset_network_state()


@pytest.fixture
def no_web_search() -> object:

    async def _none(*_args: object, **_kwargs: object) -> list[str]:
        return []

    return _none


@pytest.fixture(autouse=True)
def _fresh_queue_pause() -> None:
    from phoenixadult.services import scrape_queue

    scrape_queue._paused_until = 0.0
    scrape_queue._pause_reason = ''
    scrape_queue._kind_paused.clear()


@pytest.fixture(autouse=True)
def _fresh_rate_limits() -> None:
    from phoenixadult.utils.auth import rate_limit

    with rate_limit._lock:
        rate_limit._buckets.clear()
