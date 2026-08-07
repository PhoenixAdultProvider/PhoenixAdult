from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from phoenixadult.registry import get_all_providers
from phoenixadult.utils.plex.media_type import provider_mount_path
from tests.conftest import PLEX_UA, plex_client, seed_connection

MOUNT = provider_mount_path(get_all_providers()[0])


@pytest.fixture
def plex() -> TestClient:
    return plex_client()


def _api_key(username: str = 'plexuser') -> str:
    from phoenixadult.utils.auth import user_store

    uid = user_store.create_user(username, 'Hunter2hunter!', is_admin=True)
    return user_store.regenerate_api_key(uid)


def test_only_a_plex_media_server_user_agent_reaches_the_mount(plex: TestClient) -> None:
    assert plex.get(MOUNT).status_code == 200
    browser = TestClient(create_app(), client=('203.0.113.9', 51234), headers={'user-agent': 'Mozilla/5.0 (Windows NT 10.0)'})
    assert browser.get(MOUNT).status_code == 404, 'a browser must not be able to tell the mount exists'
    assert browser.post(f'{MOUNT}/library/metadata/matches', json={'type': 1, 'filename': 'a.mp4'}).status_code == 404
    bare = TestClient(create_app(), client=('203.0.113.9', 51234))
    assert bare.get(MOUNT).status_code == 404, 'a request with no user-agent is not Plex either'


def test_a_registered_allowlist_alone_no_longer_blocks_plex(plex: TestClient) -> None:
    from phoenixadult.services import plex_connections

    plex_connections.set_allowed_clients(seed_connection().id, ['some-registered-client'])
    assert plex.get(MOUNT).status_code == 200, 'Plex sends no client identifier when a provider is added'


def test_token_based_auth_demands_a_hook_url(monkeypatch: pytest.MonkeyPatch, plex: TestClient) -> None:
    key = _api_key()
    monkeypatch.setenv('TOKEN_BASED_AUTH', 'true')
    assert plex.get(MOUNT).status_code == 404, 'the bare mount is unreachable'
    assert plex.get(MOUNT, params={'apikey': key}).status_code == 404, 'query-param keys are gone - Plex drops them on generated requests'
    assert plex.get(f'/api/hook/{key}{MOUNT}').status_code == 200
    assert plex.post(f'/api/hook/{key}{MOUNT}/library/metadata/matches', json={'type': 1, 'filename': 'a.mp4'}).status_code == 200
    assert plex.post(f'{MOUNT}/library/metadata/matches', json={'type': 1, 'filename': 'a.mp4'}).status_code == 404


def test_the_hook_url_works_even_with_token_auth_off(plex: TestClient) -> None:
    key = _api_key()
    assert plex.get(f'/api/hook/{key}{MOUNT}').status_code == 200, 'a valid hook URL is always honored'
    assert plex.get(f'/api/hook/pa_wrong{MOUNT}').status_code == 404


def test_hook_urls_serve_only_the_provider_mount(plex: TestClient) -> None:
    key = _api_key()
    assert plex.get(f'/api/hook/{key}/config').status_code == 404, 'the capability URL must not open the admin UIs'
    assert plex.get(f'/api/hook/{key}/login').status_code == 404


def test_failed_hook_attempts_are_rate_limited_by_ip(plex: TestClient) -> None:
    _api_key()
    for _ in range(6):
        assert plex.get(f'/api/hook/pa_guess{MOUNT}').status_code == 404
    throttled = plex.get(f'/api/hook/pa_guess{MOUNT}')
    assert throttled.status_code == 429
    assert int(throttled.headers['retry-after']) > 0


def test_the_hook_token_never_reaches_the_logs(plex: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    key = _api_key()
    with caplog.at_level(5, logger='phoenixadult'):
        assert plex.get(f'/api/hook/{key}{MOUNT}').status_code == 200
        plex.get(f'/api/hook/pa_wrong-guess{MOUNT}')
    assert key not in caplog.text, 'a capability URL in the logs is a leaked credential'
    assert 'pa_wrong-guess' not in caplog.text
    assert '/api/hook/***REDACTED***/' in caplog.text


def test_token_based_auth_is_off_by_default(plex: TestClient) -> None:
    _api_key()
    assert plex.get(MOUNT).status_code == 200


def test_client_token_required_gates_matches_but_never_the_provider_url(monkeypatch: pytest.MonkeyPatch, plex: TestClient) -> None:
    from phoenixadult.services import plex_connections

    plex_connections.set_allowed_clients(seed_connection().id, ['registered-server'])
    monkeypatch.setenv('CLIENT_TOKEN_REQUIRED', 'true')
    assert plex.get(MOUNT).status_code == 200, 'the provider URL itself can never be locked, or Plex could not add it'
    match = f'{MOUNT}/library/metadata/matches'
    body = {'type': 1, 'filename': 'a.mp4'}
    assert plex.post(match, json=body).status_code == 404, 'a match without an identifier is refused'
    assert plex.post(match, json=body, headers={'X-Plex-Client-Identifier': 'stranger'}).status_code == 404
    assert plex.post(match, json=body, headers={'X-Plex-Client-Identifier': 'registered-server'}).status_code == 200
    assert plex.get(f'{MOUNT}/library/metadata/scene-x', headers={'X-Plex-Client-Identifier': 'stranger'}).status_code == 404
    assert plex.get(f'{MOUNT}/library/metadata/scene-x', headers={'X-Plex-Client-Identifier': 'registered-server'}).status_code != 404


def test_a_signed_in_session_does_not_bypass_the_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.conftest import authed_client

    monkeypatch.setenv('TOKEN_BASED_AUTH', 'true')
    admin = authed_client()
    admin.headers['user-agent'] = PLEX_UA
    assert admin.get(MOUNT).status_code == 404, 'strict mode: even an admin session needs the hook URL'


def test_provider_requests_are_traced_with_their_headers(plex: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(5, logger='phoenixadult'):
        plex.get(MOUNT, headers={'X-Plex-Client-Identifier': 'abc-123', 'X-Plex-Product': 'Plex Media Server'})
    text = caplog.text
    assert f'GET {MOUNT} from 203.0.113.9' in text, 'the trace must name the path and the caller'
    assert 'abc-123' in text and 'Plex Media Server' in text, 'the trace must dump the headers Plex sent'


def test_refused_requests_are_traced_before_they_are_refused(caplog: pytest.LogCaptureFixture) -> None:
    browser = TestClient(create_app(), client=('203.0.113.9', 51234), headers={'user-agent': 'curl/8.0'})
    with caplog.at_level(5, logger='phoenixadult'):
        assert browser.get(MOUNT).status_code == 404
    assert 'curl/8.0' in caplog.text, 'a refused request is exactly the one worth dumping'
    assert 'is not a Plex Media Server' in caplog.text


def test_the_trace_masks_credential_headers(plex: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(5, logger='phoenixadult'):
        plex.get(MOUNT, headers={'X-Plex-Token': 'super-secret', 'Authorization': 'Bearer pa_secret', 'X-Plex-Product': 'PMS'})
    assert 'PMS' in caplog.text, 'the trace should still run'
    assert 'super-secret' not in caplog.text
    assert 'pa_secret' not in caplog.text


def test_tracing_costs_nothing_when_the_level_is_off(plex: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.utils.logging import request_trace

    calls: list[str] = []
    monkeypatch.setattr(request_trace, 'verbose_enabled', lambda: False)
    monkeypatch.setattr(request_trace.logger, 'verbose', lambda *a, **k: calls.append('emitted'))
    assert plex.get(MOUNT).status_code == 200
    assert calls == [], 'no dump should be built when verbose logging is off'
