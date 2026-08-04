from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from tests.conftest import authed_cookies


def _client() -> TestClient:
    c = TestClient(create_app())
    c.cookies.update(authed_cookies())
    return c


def test_requires_auth() -> None:
    assert TestClient(create_app()).get('/plex/status', headers={'accept': 'application/json'}).status_code == 401


def test_status_reports_disabled_until_both_vars_are_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('PLEX_URL', raising=False)
    monkeypatch.delenv('PLEX_TOKEN', raising=False)
    client = _client()
    assert client.get('/plex/status').json() == {'enabled': False}

    monkeypatch.setenv('PLEX_URL', 'http://192.0.2.10:32400')
    assert client.get('/plex/status').json() == {'enabled': False}

    monkeypatch.setenv('PLEX_TOKEN', 'test-token')
    assert client.get('/plex/status').json() == {'enabled': True}


def test_reconcile_progress_reports_the_run_state() -> None:
    body = _client().get('/plex/reconcile/progress').json()
    assert set(body) == {'active', 'total', 'inspected'}
    assert body['active'] is False


def test_reconcile_409s_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('PLEX_URL', raising=False)
    monkeypatch.delenv('PLEX_TOKEN', raising=False)
    r = _client().post('/plex/reconcile')
    assert r.status_code == 409
    assert 'PLEX_URL' in r.json()['error']


def test_reconcile_rejects_a_bad_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('PLEX_URL', 'http://192.0.2.10:32400')
    monkeypatch.setenv('PLEX_TOKEN', 'test-token')
    r = _client().post('/plex/reconcile?limit=abc')
    assert r.status_code == 400
