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
    assert "'theme', ...(isAdmin() ? ['logs'] : [])];" in body
    assert 'THEME_TAB, ...(isAdmin() ? [LOGS_TAB] : [])];' in body
    assert '[...tabNames(), ...extraTabs()]' in body
    assert 'id="tab-logs"' in body
    assert 'white-space: pre;' in body
    assert 'overflow: auto;' in body
    assert 'touch-action: pan-x pan-y' in body
    assert 'user-select: text' in body


def test_reconcile_shows_a_scene_progress_bar(client: TestClient) -> None:
    body = client.get('/config').text
    assert 'id="plex-reconcile-progress"' in body
    assert "fetch(api(connPath('/reconcile/progress')))" in body
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


def _member_client() -> TestClient:
    from phoenixadult.utils.auth import user_store

    uid = user_store.create_user('member', 'pw-member', is_admin=False)
    token = user_store.create_session(uid, 'pytest')
    member = TestClient(create_app())
    member.cookies.set('pa_session', token)
    return member


def test_non_admins_get_a_filtered_state_and_no_env_writes(client: TestClient) -> None:
    member = _member_client()
    state = member.get('/config/api/state').json()
    assert state['groups'] == [] and state['tabs'] == [] and state['overridesPath'] == ''
    assert state['metadataapi'] == {'hasToken': False}
    assert member.post('/config/api/save', json={'updates': {'LOG_LEVEL': 'info'}}).status_code == 403
    assert member.post('/config/api/reset', json={}).status_code == 403
    assert member.post('/config/api/restart').status_code == 403
    assert member.get('/config/api/logs').status_code == 403
    assert member.get('/config/api/clients').status_code == 403
    assert member.get('/config').status_code == 200


def test_metadataapi_tokens_are_per_user(client: TestClient) -> None:
    member = _member_client()
    assert client.post('/config/api/metadataapi', json={'token': 'admin-tok'}).json() == {'hasToken': True}
    assert member.get('/config/api/state').json()['metadataapi'] == {'hasToken': False}
    assert member.post('/config/api/metadataapi', json={'token': 'member-tok'}).json() == {'hasToken': True}

    from phoenixadult.utils.auth import user_store, user_tokens

    users = {u['username']: u['id'] for u in user_store.list_users()}
    assert user_tokens.token_for_user(users['tester']) == 'admin-tok'
    assert user_tokens.token_for_user(users['member']) == 'member-tok'
    assert client.post('/config/api/metadataapi', json={}).json() == {'hasToken': False}
    assert user_tokens.token_for_user(users['member']) == 'member-tok'


def test_theme_saves_to_the_calling_user_only(client: TestClient) -> None:
    member = _member_client()
    assert client.post('/config/api/theme', json={'dark': 'forest', 'light': 'meadow'}).status_code == 200
    assert member.post('/config/api/theme', json={'dark': 'midnight', 'light': 'day'}).status_code == 200
    assert client.post('/config/api/theme', json={'dark': 'nope'}).status_code == 400

    from phoenixadult.utils.auth import user_store

    rows = {r['username']: r for r in user_store.list_users()}
    admin_page = client.get('/config').text
    assert '"dark": "forest"' in admin_page and '"light": "meadow"' in admin_page
    member_page = member.get('/config').text
    assert '"dark": "midnight"' in member_page and '"light": "day"' in member_page
    assert rows is not None


def test_client_hits_record_plex_headers_for_admins(client: TestClient) -> None:
    from phoenixadult.utils.plex import client_hits

    client_hits.clear()
    client.post(
        '/phoenixadult/movies/library/metadata/matches',
        json={'type': 1, 'title': 'nope'},
        headers={'x-plex-client-identifier': 'cid-123', 'x-plex-device-name': 'MAR', 'x-plex-product': 'Plex Media Server'},
    )
    hits = client.get('/config/api/clients').json()['clients']
    assert len(hits) == 1
    assert hits[0]['clientId'] == 'cid-123'
    assert hits[0]['headers']['x-plex-device-name'] == 'MAR'
    assert hits[0]['count'] == 1 and hits[0]['lastPath'].endswith('/matches')


def test_the_config_page_carries_the_new_admin_sections(client: TestClient) -> None:
    body = client.get('/config').text
    assert 'id="tab-clients"' in body
    assert 'function metadataApiCardHtml()' in body
    assert 'function imageOverrideCardHtml()' in body
    assert 'id="conn-image-base"' in body
    assert 'saveThemeChoice' in body


def test_the_logs_tab_breaks_out_of_the_page_width_but_the_header_stays_put(client: TestClient) -> None:
    body = client.get('/config').text
    assert 'body.logs-wide #tab-logs { max-width: none; }' in body
    assert 'scrollbar-gutter: stable;' in body
    assert 'h1, .sub, .toolbar, .tabbar, #tabpanes, #tab-plex, #tab-logs, #tab-theme { max-width: 1092px; margin-inline: auto; }' in body
    assert "document.body.classList.toggle('logs-wide', name === 'logs');" in body
    assert 'function logFill()' in body
    assert "window.addEventListener('resize'" in body
    assert 'max-width: 1092px' in body


def test_production_locks_the_redaction_flags_out_of_the_ui(monkeypatch: pytest.MonkeyPatch) -> None:
    keys = {v['key'] for g in authed_client().get('/config/api/state').json()['groups'] for v in g['vars']}
    assert {'LOG_REDACT_HOSTS', 'LOG_REDACT_TOKEN'} <= keys, 'in dev the switches are offered'
    monkeypatch.setenv('NODE_ENV', 'production')
    prod_keys = {v['key'] for g in authed_client().get('/config/api/state').json()['groups'] for v in g['vars']}
    assert 'LOG_REDACT_HOSTS' not in prod_keys and 'LOG_REDACT_TOKEN' not in prod_keys, 'production always redacts; the switches disappear'
