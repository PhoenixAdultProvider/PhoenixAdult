from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.app_factory import create_app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv('ADMIN_TOKEN', raising=False)
    return TestClient(create_app())


def test_cross_site_post_rejected(client: TestClient) -> None:
    r = client.post('/config/api/save', json={'key': 'X', 'value': 'y'}, headers={'Sec-Fetch-Site': 'cross-site'})
    assert r.status_code == 403


def test_same_origin_post_passes_guard(client: TestClient) -> None:
    r = client.post('/config/api/save', json={'key': 'NOPE', 'value': 'y'}, headers={'Sec-Fetch-Site': 'same-origin'})
    assert r.status_code != 403


def test_headerless_post_passes_guard(client: TestClient) -> None:
    r = client.post('/config/api/save', json={'key': 'NOPE', 'value': 'y'})
    assert r.status_code != 403


def test_cross_site_get_still_allowed(client: TestClient) -> None:
    r = client.get('/config/api/state', headers={'Sec-Fetch-Site': 'cross-site'})
    assert r.status_code == 200
