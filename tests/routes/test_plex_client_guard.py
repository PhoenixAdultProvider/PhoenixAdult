from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from phoenixadult.registry import get_all_providers
from phoenixadult.utils.plex.media_type import provider_mount_path
from tests.conftest import seed_connection

APPROVED = '5c206a0663a94ba68cad5f9c74abf71fa16eb083'
MOUNT = provider_mount_path(get_all_providers()[0])


def _allow(*client_ids: str) -> None:
    from phoenixadult.services import plex_connections

    connection = seed_connection()
    plex_connections.set_allowed_clients(connection.id, list(client_ids))


@pytest.fixture
def client() -> TestClient:
    _allow(APPROVED, 'second-server-id')
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


def test_loopback_is_exempt() -> None:
    _allow(APPROVED)
    local = TestClient(create_app(), client=('127.0.0.1', 51234))
    assert local.get(MOUNT).status_code == 200


def test_api_key_is_exempt(client: TestClient) -> None:
    from phoenixadult.utils.auth import user_store

    uid = user_store.create_user('plexuser', 'pw', is_admin=True)
    key = user_store.regenerate_api_key(uid)
    assert client.get(MOUNT, headers={'x-api-key': key}).status_code == 200


def test_empty_union_disables_the_guard() -> None:
    remote = TestClient(create_app(), client=('203.0.113.9', 51234))
    assert remote.get(MOUNT).status_code == 200


def test_any_connections_client_id_is_accepted() -> None:
    from phoenixadult.services import plex_connections
    from phoenixadult.utils.auth import user_store

    _allow(APPROVED)
    other_user = user_store.create_user('second', 'pw-second', is_admin=False)
    second = plex_connections.create(other_user, 'Their Server')
    plex_connections.set_allowed_clients(second, ['their-server-id'])

    remote = TestClient(create_app(), client=('203.0.113.9', 51234))
    assert remote.get(MOUNT, headers={'X-Plex-Client-Identifier': 'their-server-id'}).status_code == 200


def test_the_rejection_log_names_the_client_and_the_remedy(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level('WARNING'):
        assert client.get(MOUNT, headers={'X-Plex-Client-Identifier': 'someone-else'}).status_code == 403
    message = caplog.text
    assert 'someone-else' in message, 'the log must name the identifier that was refused'
    assert '203.0.113.9' in message, 'the log must name where the request came from'
    assert 'not one of the 2 registered' in message, 'the log must say how many identifiers are allowed'
    assert 'Config > Clients' in message and 'Allowed Plex Clients' in message, 'the log must say how to fix it'
    assert message.isascii(), 'log messages must survive a cp1252 console on Windows'


def test_the_rejection_log_calls_out_a_missing_header(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level('WARNING'):
        assert client.get(MOUNT).status_code == 403
    assert 'no X-Plex-Client-Identifier header' in caplog.text
    assert 'Clear the list' in caplog.text, 'allowlisting cannot match an absent identifier, so say so'


def test_allowed_requests_say_which_rule_let_them_through(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level('DEBUG'):
        assert client.get(MOUNT, headers={'X-Plex-Client-Identifier': APPROVED}).status_code == 200
    assert f'client "{APPROVED}" is registered' in caplog.text
