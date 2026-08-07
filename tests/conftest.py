from __future__ import annotations

import os
import shutil
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


def _seed_session(is_admin: bool = True) -> str:
    from phoenixadult.utils.auth import user_store

    uid = user_store.oldest_admin_id() if user_store.user_count() else user_store.create_user('tester', 'pytest-pw', is_admin=is_admin)
    assert uid is not None
    return user_store.create_session(uid, 'pytest')


def authed_cookies() -> dict[str, str]:
    return {'pa_session': _seed_session()}


def seed_connection(name: str = 'Test Server', url: str = 'http://192.0.2.10:32400', token: str = 'test-token', **fields: Any) -> Any:
    from phoenixadult.services import plex_connections
    from phoenixadult.utils.auth import user_store

    owner = user_store.oldest_admin_id() or user_store.create_user('tester', 'pytest-pw', is_admin=True)
    connection_id = plex_connections.create(owner, name)
    plex_connections.update_fields(connection_id, {'serverUrl': url, **fields})
    if token:
        plex_connections.save_token(connection_id, token)
    connection = plex_connections.get(connection_id)
    assert connection is not None
    return connection


def authed_client(app: Any = None, is_admin: bool = True) -> Any:
    from starlette.testclient import TestClient

    from phoenixadult.app_factory import create_app

    token = _seed_session(is_admin)
    client = TestClient(app or create_app())
    client.cookies.set('pa_session', token)
    return client


@pytest.fixture
def no_web_search() -> object:

    async def _none(*_args: object, **_kwargs: object) -> list[str]:
        return []

    return _none


@pytest.fixture(autouse=True)
def _fresh_rate_limits() -> None:
    from phoenixadult.utils.auth import rate_limit

    with rate_limit._lock:
        rate_limit._buckets.clear()


PLEX_UA = 'PlexMediaServer/1.43.3.10861-07dfddaeb'


def plex_client(app: Any = None, host: str = '203.0.113.9') -> Any:
    from starlette.testclient import TestClient

    from phoenixadult.app_factory import create_app

    return TestClient(app or create_app(), client=(host, 51234), headers={'user-agent': PLEX_UA})
