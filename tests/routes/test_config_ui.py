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
    assert 'class="toolbar"' in body  # styled UI, not the old stub
    assert 'const STATE =' in body  # client-rendered state
    assert '__STATE_JSON__' not in body  # placeholder was substituted


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
