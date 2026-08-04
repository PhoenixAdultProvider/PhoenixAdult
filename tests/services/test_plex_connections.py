from __future__ import annotations

import pytest

from phoenixadult.services import plex_connections as pc
from phoenixadult.utils.auth import user_store


def _owner() -> int:
    return user_store.create_user('owner', 'pw-owner', is_admin=True)


def test_create_and_read_back() -> None:
    uid = _owner()
    cid = pc.create(uid, 'Home')
    connection = pc.get_owned(uid, cid)
    assert connection is not None
    assert connection.name == 'Home' and connection.client_id and connection.has_token is False
    assert pc.get_owned(uid + 999, cid) is None


def test_token_is_encrypted_at_rest_and_recoverable() -> None:
    from phoenixadult.utils import db

    uid = _owner()
    cid = pc.create(uid, 'Home')
    pc.save_token(cid, 'plex-secret')

    stored = db.connect().execute('SELECT token_encrypted FROM plex_connections WHERE id = ?', (cid,)).fetchone()['token_encrypted']
    assert stored and 'plex-secret' not in stored
    assert pc.token_for(cid) == 'plex-secret'


def test_token_survives_nothing_when_absent() -> None:
    uid = _owner()
    cid = pc.create(uid, 'Home')
    assert pc.token_for(cid) is None


def test_update_fields_and_allowed_clients() -> None:
    uid = _owner()
    cid = pc.create(uid, 'Home')
    pc.update_fields(cid, {'serverUrl': 'http://192.0.2.10:32400', 'updateChannel': 'beta', 'imageBaseUrl': 'http://lan:3000'})
    pc.set_allowed_clients(cid, ['bbb', 'aaa', 'aaa', ' '])

    connection = pc.get(cid)
    assert connection is not None
    assert connection.server_url == 'http://192.0.2.10:32400'
    assert connection.update_channel == 'beta'
    assert connection.image_base_url == 'http://lan:3000'
    assert connection.allowed_clients == ('aaa', 'bbb')


def test_allowed_client_union_spans_users_and_refreshes() -> None:
    a = _owner()
    b = user_store.create_user('second', 'pw-second', is_admin=False)
    pc.set_allowed_clients(pc.create(a, 'A'), ['id-a'])
    second = pc.create(b, 'B')
    pc.set_allowed_clients(second, ['id-b'])
    assert pc.allowed_client_union() == frozenset({'id-a', 'id-b'})

    pc.delete(second)
    assert pc.allowed_client_union() == frozenset({'id-a'})


def test_deleting_a_user_cascades_their_connections() -> None:
    from phoenixadult.utils import db

    uid = _owner()
    pc.set_allowed_clients(pc.create(uid, 'Home'), ['abc'])
    user_store.delete_user(uid)
    assert db.connect().execute('SELECT COUNT(*) FROM plex_connections').fetchone()[0] == 0
    assert db.connect().execute('SELECT COUNT(*) FROM plex_connection_clients').fetchone()[0] == 0


def test_env_migration_moves_settings_into_the_first_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('PLEX_URL', 'http://plex.lan:32400')
    monkeypatch.setenv('PLEX_TOKEN', 'env-token')
    monkeypatch.setenv('PLEX_CLIENT_ID', 'client-42')
    monkeypatch.setenv('PLEX_CLIENT_ALLOWLIST', 'server-a,server-b')
    monkeypatch.setenv('PLEX_UPDATE_CHANNEL', 'beta')
    uid = _owner()

    assert pc.migrate_env_connection() == 'plex.lan'
    connections = pc.list_for_user(uid)
    assert len(connections) == 1
    migrated = connections[0]
    assert migrated.server_url == 'http://plex.lan:32400'
    assert migrated.client_id == 'client-42'
    assert migrated.update_channel == 'beta'
    assert migrated.allowed_clients == ('server-a', 'server-b')
    assert pc.token_for(migrated.id) == 'env-token'


def test_env_migration_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('PLEX_URL', 'http://plex.lan:32400')
    monkeypatch.setenv('PLEX_TOKEN', 'env-token')
    uid = _owner()

    assert pc.migrate_env_connection() == 'plex.lan'
    assert pc.migrate_env_connection() is None
    assert len(pc.list_for_user(uid)) == 1


def test_env_migration_needs_a_user_and_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('PLEX_URL', raising=False)
    monkeypatch.delenv('PLEX_TOKEN', raising=False)
    _owner()
    assert pc.migrate_env_connection() is None

    monkeypatch.setenv('PLEX_URL', 'http://plex.lan:32400')
    user_store.delete_user(user_store.oldest_admin_id() or 0)
    assert pc.migrate_env_connection() is None
