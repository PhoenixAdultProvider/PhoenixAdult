from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from tests.conftest import authed_client

TOKEN = 'cfgtoken'


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    return authed_client()


def test_config_requires_auth() -> None:
    assert TestClient(create_app()).get('/config', headers={'accept': 'application/json'}).status_code == 401


def test_config_page_renders_styled(client: TestClient) -> None:
    r = client.get('/config')
    assert r.status_code == 200
    body = r.text
    assert 'PhoenixAdult Config' in body
    assert 'class="toolbar"' in body
    assert 'const STATE =' in body
    assert '__STATE_JSON__' not in body


def test_config_api_state(client: TestClient) -> None:
    r = client.get('/config/api/state')
    assert r.status_code == 200
    data = r.json()
    assert 'groups' in data and 'overridesPath' in data
    keys = {v['key'] for g in data['groups'] for v in g['vars']}
    assert 'LOG_LEVEL' in keys


def test_config_api_save_rejects_unknown_key(client: TestClient) -> None:
    r = client.post('/config/api/save', json={'updates': {'NOPE': 'x'}})
    assert r.status_code == 400


def test_config_api_restart_reloads_in_dev(client: TestClient, tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path

    from phoenixadult.routes import env_routes

    monkeypatch.setenv('NODE_ENV', 'development')
    sentinel = Path(str(tmp_path)) / 'main.py'
    sentinel.write_bytes(b'x')
    monkeypatch.setattr(env_routes, '_MAIN_PY', sentinel)
    r = client.post('/config/api/restart')
    assert r.status_code == 200 and r.json()['method'] == 'reload'


def test_config_api_restart_shuts_down_in_prod(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.routes import env_routes

    monkeypatch.setenv('NODE_ENV', 'production')
    killed: list[int] = []
    monkeypatch.setattr(env_routes.os, 'kill', lambda _pid, sig: killed.append(sig))
    r = client.post('/config/api/restart')
    assert r.status_code == 200 and r.json()['method'] == 'shutdown'
    assert killed


def test_config_page_has_a_mobile_layout() -> None:
    body = authed_client().get('/config').text
    assert '@media (max-width: 720px)' in body
    assert 'toolbarToggle' in body
    assert 'attachTouchDrag' in body
    assert 'touch-action: none' in body
    assert 'style="flex:0 0 170px' not in body
    assert 'style="flex:1 1 260px' not in body


def test_logs_endpoint_requires_auth_and_serves_the_session(client: TestClient) -> None:
    from phoenixadult.utils.logging.logger import logger

    assert TestClient(create_app()).get('/config/api/logs', headers={'accept': 'application/json'}).status_code == 401

    logger.info('log-viewer-test', 'a distinctive line')
    data = client.get('/config/api/logs').json()
    assert data['reset'] is True and data['choices'] == [50, 100, 200, 500, 1000]
    assert any('a distinctive line' in line for line in data['lines'])

    caught_up = client.get('/config/api/logs', params={'since': data['seq']}).json()
    assert caught_up['lines'] == [] and caught_up['reset'] is False

    logger.info('log-viewer-test', 'one more line')
    delta = client.get('/config/api/logs', params={'since': data['seq']}).json()
    assert len(delta['lines']) == 1 and 'one more line' in delta['lines'][0]


def test_logs_tab_is_last_and_never_wraps(client: TestClient) -> None:
    body = client.get('/config').text
    assert "const LOGS_TAB = 'Logs';" in body
    assert "return [...tabNames().map(tabSlug), 'plex', 'theme', 'logs'];" in body
    assert '[...tabNames(), PLEX_TAB, THEME_TAB, LOGS_TAB]' in body
    assert 'id="tab-logs"' in body
    assert 'white-space: pre;' in body
    assert 'overflow: auto;' in body
    assert 'touch-action: pan-x pan-y' in body
    assert 'user-select: text' in body


def test_reconcile_shows_a_scene_progress_bar(client: TestClient) -> None:
    body = client.get('/config').text
    assert 'id="plex-reconcile-progress"' in body
    assert "fetch(api('/plex/reconcile/progress'))" in body
    assert "' of ' + p.total + ' scenes inspected'" in body
    assert 'startReconcileProgress();' in body and 'stopReconcileProgress();' in body


def test_the_theme_tab_sits_before_logs_with_pickers_and_a_preview(client: TestClient) -> None:
    body = client.get('/config').text
    assert "const THEME_TAB = 'Theme';" in body
    assert 'id="tab-theme"' in body
    assert 'id="themeDark"' in body and 'id="themeLight"' in body
    assert 'Element Preview' in body
    assert 'data-theme-preview=' in body
    assert 'previewSamples' in body
    for var in ('--female', '--male', '--trans', '--gender-none'):
        assert f'var({var})' in body


def test_the_log_toolbar_offers_every_control(client: TestClient) -> None:
    body = client.get('/config').text
    for marker in ('id="logFilter"', 'id="logMaxSel"', 'id="logPauseBtn"', 'onclick="logClear()"', 'onclick="copyLog(this)"'):
        assert marker in body
    assert 'const LOG_CHOICES = [50, 100, 200, 500, 1000];' in body
    assert 'The last 200 lines this server has logged' not in body


def test_the_line_limit_caps_what_the_endpoint_returns(client: TestClient) -> None:
    from phoenixadult.utils.logging.logger import logger

    for i in range(30):
        logger.info('log-limit-test', f'limited line {i}')

    data = client.get('/config/api/logs', params={'limit': 5}).json()
    assert len(data['lines']) == 5
    assert 'limited line 29' in data['lines'][-1]

    assert len(client.get('/config/api/logs', params={'limit': 99999}).json()['lines']) <= 1000
    assert len(client.get('/config/api/logs', params={'limit': 0}).json()['lines']) == 1


def test_the_log_view_shows_the_same_redaction_the_file_gets(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.utils.logging.logger import logger

    monkeypatch.setenv('LOG_REDACT_TOKEN', 'true')
    logger.info('log-viewer-test', 'fetching ?token=abcdef0123456789 now')

    lines = client.get('/config/api/logs').json()['lines']
    hit = next(line for line in lines if 'fetching' in line)
    assert 'abcdef0123456789' not in hit
    assert 'token=***REDACTED***' in hit


def test_the_logs_tab_breaks_out_of_the_page_width_but_the_header_stays_put(client: TestClient) -> None:
    body = client.get('/config').text
    assert 'body.logs-wide #tab-logs { max-width: none; }' in body
    assert 'scrollbar-gutter: stable;' in body
    assert 'h1, .sub, .toolbar, .tabbar, #tabpanes, #tab-plex, #tab-logs, #tab-theme { max-width: 1092px; margin-inline: auto; }' in body
    assert "document.body.classList.toggle('logs-wide', name === 'logs');" in body
    assert 'function logFill()' in body
    assert "window.addEventListener('resize'" in body
    assert 'max-width: 1092px' in body
