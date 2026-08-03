from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from phoenixadult.registry import get_all_providers
from phoenixadult.utils.plex.media_type import provider_mount_path

APPROVED = '5c206a0663a94ba68cad5f9c74abf71fa16eb083'
MOUNT = provider_mount_path(get_all_providers()[0])


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv('PLEX_CLIENT_ALLOWLIST', f'{APPROVED},second-server-id')
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    return TestClient(create_app(), client=('203.0.113.9', 51234))


def test_unapproved_client_gets_403(client: TestClient) -> None:
    assert client.get(MOUNT).status_code == 403
    assert client.get(MOUNT, headers={'X-Plex-Client-Identifier': 'someone-else'}).status_code == 403
    r = client.post(f'{MOUNT}/library/metadata/matches', json={'type': 1, 'filename': 'a.mp4'})
    assert r.status_code == 403
    assert client.get(f'{MOUNT}/library/metadata/scene-nubilefilms-abc').status_code == 403


def test_approved_client_is_served(client: TestClient) -> None:
    headers = {'X-Plex-Client-Identifier': APPROVED}
    assert client.get(MOUNT, headers=headers).status_code == 200
    r = client.post(f'{MOUNT}/library/metadata/matches', json={'type': 1, 'filename': 'a.mp4'}, headers=headers)
    assert r.status_code == 200


def test_loopback_is_exempt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('PLEX_CLIENT_ALLOWLIST', APPROVED)
    local = TestClient(create_app(), client=('127.0.0.1', 51234))
    assert local.get(MOUNT).status_code == 200


def test_admin_token_is_exempt(client: TestClient) -> None:
    assert client.get(MOUNT, headers={'X-Admin-Token': 'tok'}).status_code == 200


def test_empty_allowlist_disables_the_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('PLEX_CLIENT_ALLOWLIST', raising=False)
    remote = TestClient(create_app(), client=('203.0.113.9', 51234))
    assert remote.get(MOUNT).status_code == 200
