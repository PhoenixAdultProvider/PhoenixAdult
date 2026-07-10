from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.app_factory import create_app

TOKEN = 'cfgtoken'


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv('ADMIN_TOKEN', TOKEN)
    return TestClient(create_app())


def test_config_requires_auth(client: TestClient) -> None:
    assert client.get('/config').status_code == 401


def test_config_page_renders_styled(client: TestClient) -> None:
    r = client.get('/config', params={'token': TOKEN})
    assert r.status_code == 200
    body = r.text
    assert 'PhoenixAdult Config' in body
    assert 'class="toolbar"' in body
    assert 'const STATE =' in body
    assert '__STATE_JSON__' not in body


def test_config_api_state(client: TestClient) -> None:
    r = client.get('/config/api/state', params={'token': TOKEN})
    assert r.status_code == 200
    data = r.json()
    assert 'groups' in data and 'overridesPath' in data
    keys = {v['key'] for g in data['groups'] for v in g['vars']}
    assert 'LOG_LEVEL' in keys


def test_config_api_save_rejects_unknown_key(client: TestClient) -> None:
    r = client.post('/config/api/save', params={'token': TOKEN}, json={'updates': {'NOPE': 'x'}})
    assert r.status_code == 400


def test_config_api_restart_reloads_in_dev(client: TestClient, tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path

    from app.routes import env_routes

    monkeypatch.setenv('NODE_ENV', 'development')
    sentinel = Path(str(tmp_path)) / 'main.py'
    sentinel.write_bytes(b'x')
    monkeypatch.setattr(env_routes, '_MAIN_PY', sentinel)
    r = client.post('/config/api/restart', params={'token': TOKEN})
    assert r.status_code == 200 and r.json()['method'] == 'reload'


def test_config_api_restart_shuts_down_in_prod(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routes import env_routes

    monkeypatch.setenv('NODE_ENV', 'production')
    killed: list[int] = []
    monkeypatch.setattr(env_routes.os, 'kill', lambda _pid, sig: killed.append(sig))
    r = client.post('/config/api/restart', params={'token': TOKEN})
    assert r.status_code == 200 and r.json()['method'] == 'shutdown'
    assert killed
