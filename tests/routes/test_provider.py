from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.app_factory import create_app
from app.registry import DEFAULT_PROVIDER_ID, get_all_providers, provider_mount_path


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_health(client: TestClient) -> None:
    r = client.get('/health')
    assert r.status_code == 200
    assert r.json() == {'status': 'ok'}


def test_providers_endpoint(client: TestClient) -> None:
    r = client.get('/providers')
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]['id'] == DEFAULT_PROVIDER_ID
    assert isinstance(data[0]['sites'], list)


def test_provider_capability_declaration(client: TestClient) -> None:
    mount = provider_mount_path(get_all_providers()[0])
    r = client.get(mount)
    assert r.status_code == 200
    body = r.json()
    assert body['MediaProvider']['title'] == 'PhoenixAdult'
    assert body['MediaProvider']['Types'][0]['type'] == 1


def test_match_empty_when_no_site(client: TestClient) -> None:
    mount = provider_mount_path(get_all_providers()[0])
    r = client.post(
        f'{mount}/library/metadata/matches',
        json={'type': 1, 'filename': 'Unknown.Site.2024.01.02.mp4', 'manual': 1, 'includeAdult': 1},
    )
    assert r.status_code == 200
    assert r.json()['MediaContainer']['totalSize'] == 0
