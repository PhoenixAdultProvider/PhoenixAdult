from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app


def _client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    return TestClient(create_app())


def test_requires_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)
    assert client.get('/plex/status').status_code == 401


def test_status_reports_disabled_until_both_vars_are_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('PLEX_URL', raising=False)
    monkeypatch.delenv('PLEX_TOKEN', raising=False)
    client = _client(monkeypatch)
    hdr = {'x-admin-token': 'tok'}
    assert client.get('/plex/status', headers=hdr).json() == {'enabled': False}

    monkeypatch.setenv('PLEX_URL', 'http://192.0.2.10:32400')
    assert client.get('/plex/status', headers=hdr).json() == {'enabled': False}

    monkeypatch.setenv('PLEX_TOKEN', 'test-token')
    assert client.get('/plex/status', headers=hdr).json() == {'enabled': True}


def test_reconcile_409s_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('PLEX_URL', raising=False)
    monkeypatch.delenv('PLEX_TOKEN', raising=False)
    client = _client(monkeypatch)
    r = client.post('/plex/reconcile', headers={'x-admin-token': 'tok'})
    assert r.status_code == 409
    assert 'PLEX_URL' in r.json()['error']


def test_reconcile_rejects_a_bad_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('PLEX_URL', 'http://192.0.2.10:32400')
    monkeypatch.setenv('PLEX_TOKEN', 'test-token')
    client = _client(monkeypatch)
    r = client.post('/plex/reconcile?limit=abc', headers={'x-admin-token': 'tok'})
    assert r.status_code == 400
