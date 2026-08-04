from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from tests.conftest import authed_client


@pytest.fixture
def client() -> TestClient:
    return authed_client()


def test_cross_site_post_rejected(client: TestClient) -> None:
    r = client.post('/config/api/save', json={'updates': {}}, headers={'Sec-Fetch-Site': 'cross-site'})
    assert r.status_code == 403


def test_cross_origin_post_rejected(client: TestClient) -> None:
    r = client.post('/config/api/save', json={'updates': {}}, headers={'Origin': 'https://evil.example'})
    assert r.status_code == 403


def test_same_origin_post_passes_guard(client: TestClient) -> None:
    r = client.post('/config/api/save', json={'updates': {'NOPE': 'y'}}, headers={'Sec-Fetch-Site': 'same-origin'})
    assert r.status_code != 403


def test_headerless_post_passes_guard(client: TestClient) -> None:
    r = client.post('/config/api/save', json={'updates': {'NOPE': 'y'}})
    assert r.status_code != 403


def test_api_key_post_is_exempt_from_csrf() -> None:
    from phoenixadult.utils.auth import user_store

    app = create_app()
    uid = user_store.create_user('csrfuser', 'pw', is_admin=True)
    key = user_store.regenerate_api_key(uid)
    r = TestClient(app).post('/config/api/save', json={'updates': {'NOPE': 'y'}}, headers={'Sec-Fetch-Site': 'cross-site', 'x-api-key': key})
    assert r.status_code != 403


def test_cross_site_get_still_allowed(client: TestClient) -> None:
    r = client.get('/config/api/state', headers={'Sec-Fetch-Site': 'cross-site'})
    assert r.status_code == 200
