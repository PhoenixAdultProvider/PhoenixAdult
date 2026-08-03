from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from phoenixadult.registry import get_all_providers
from phoenixadult.utils.plex.media_type import provider_mount_path


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_health(client: TestClient) -> None:
    r = client.get('/health')
    assert r.status_code == 200
    assert r.json() == {'status': 'ok'}


def test_favicon_routes(client: TestClient) -> None:
    ico = client.get('/favicon.ico')
    assert ico.status_code == 200
    assert ico.headers['content-type'] == 'image/x-icon'
    svg = client.get('/favicon.svg')
    assert svg.status_code == 200
    assert 'image/svg+xml' in svg.headers['content-type']


def test_provider_capability_declaration(client: TestClient) -> None:
    mount = provider_mount_path(get_all_providers()[0])
    r = client.get(mount)
    assert r.status_code == 200
    body = r.json()
    assert body['MediaProvider']['title'] == 'PhoenixAdult'
    assert body['MediaProvider']['Types'][0]['type'] == 1


def test_match_400_when_no_site(client: TestClient) -> None:
    mount = provider_mount_path(get_all_providers()[0])
    r = client.post(
        f'{mount}/library/metadata/matches',
        json={'type': 1, 'filename': 'Unknown.Site.2024.01.02.mp4', 'manual': 1, 'includeAdult': 1},
    )
    assert r.status_code == 400
    assert 'no registry site' in r.json()['error']


def test_match_400_when_no_parse_source(client: TestClient) -> None:
    mount = provider_mount_path(get_all_providers()[0])
    r = client.post(f'{mount}/library/metadata/matches', json={'type': 1, 'manual': 1, 'includeAdult': 1})
    assert r.status_code == 400
    assert 'no title or filename' in r.json()['error']


def test_match_suppressed_stays_empty_200(client: TestClient) -> None:
    mount = provider_mount_path(get_all_providers()[0])
    r = client.post(f'{mount}/library/metadata/matches', json={'type': 1, 'filename': 'Whatever.mp4'})
    assert r.status_code == 200
    assert r.json()['MediaContainer']['totalSize'] == 0


def test_metadata_400_on_malformed_rating_key(client: TestClient) -> None:
    mount = provider_mount_path(get_all_providers()[0])
    r = client.get(f'{mount}/library/metadata/not-a-real-key-format!!')
    assert r.status_code == 400
    assert 'Bad request' in r.json()['error']


def test_metadata_400_on_unknown_site_in_rating_key(client: TestClient) -> None:
    mount = provider_mount_path(get_all_providers()[0])
    r = client.get(f'{mount}/library/metadata/scene-notarealsite123-YWJj')
    assert r.status_code == 400
    assert 'no registry site' in r.json()['error']
