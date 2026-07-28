from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app

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

    from phoenixadult.routes import env_routes

    monkeypatch.setenv('NODE_ENV', 'development')
    sentinel = Path(str(tmp_path)) / 'main.py'
    sentinel.write_bytes(b'x')
    monkeypatch.setattr(env_routes, '_MAIN_PY', sentinel)
    r = client.post('/config/api/restart', params={'token': TOKEN})
    assert r.status_code == 200 and r.json()['method'] == 'reload'


def test_config_api_restart_shuts_down_in_prod(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.routes import env_routes

    monkeypatch.setenv('NODE_ENV', 'production')
    killed: list[int] = []
    monkeypatch.setattr(env_routes.os, 'kill', lambda _pid, sig: killed.append(sig))
    r = client.post('/config/api/restart', params={'token': TOKEN})
    assert r.status_code == 200 and r.json()['method'] == 'shutdown'
    assert killed


def test_config_page_has_a_mobile_layout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('ADMIN_TOKEN', raising=False)
    body = TestClient(create_app()).get('/config').text
    assert '@media (max-width: 720px)' in body
    assert 'toolbarToggle' in body
    assert 'attachTouchDrag' in body
    assert 'touch-action: none' in body
    assert 'style="flex:0 0 170px' not in body
    assert 'style="flex:1 1 260px' not in body


def test_logs_endpoint_requires_auth_and_serves_the_session(client: TestClient) -> None:
    from phoenixadult.utils.logging.logger import logger

    assert client.get('/config/api/logs').status_code == 401

    logger.info('log-viewer-test', 'a distinctive line')
    data = client.get('/config/api/logs', params={'token': TOKEN}).json()
    assert data['reset'] is True and data['max'] == 200
    assert any('a distinctive line' in line for line in data['lines'])

    caught_up = client.get('/config/api/logs', params={'token': TOKEN, 'since': data['seq']}).json()
    assert caught_up['lines'] == [] and caught_up['reset'] is False

    logger.info('log-viewer-test', 'one more line')
    delta = client.get('/config/api/logs', params={'token': TOKEN, 'since': data['seq']}).json()
    assert len(delta['lines']) == 1 and 'one more line' in delta['lines'][0]


def test_logs_tab_is_last_and_never_wraps(client: TestClient) -> None:
    body = client.get('/config', params={'token': TOKEN}).text
    assert "const LOGS_TAB = 'Logs';" in body
    assert "return [...tabNames().map(tabSlug), 'plex', 'logs'];" in body
    assert '[...tabNames(), PLEX_TAB, LOGS_TAB]' in body
    assert 'id="tab-logs"' in body
    assert 'white-space: pre;' in body
    assert 'overflow: auto;' in body
    assert 'touch-action: pan-x pan-y' in body
    assert 'user-select: text' in body


def test_the_log_view_shows_the_same_redaction_the_file_gets(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.utils.logging.logger import logger

    monkeypatch.setenv('LOG_REDACT_TOKEN', 'true')
    logger.info('log-viewer-test', 'fetching ?token=abcdef0123456789 now')

    lines = client.get('/config/api/logs', params={'token': TOKEN}).json()['lines']
    hit = next(line for line in lines if 'fetching' in line)
    assert 'abcdef0123456789' not in hit
    assert 'token=***REDACTED***' in hit
