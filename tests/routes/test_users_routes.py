from __future__ import annotations

from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from phoenixadult.utils.auth import user_store
from tests.support import authed_client


def _member_client() -> TestClient:
    uid = user_store.create_user('member', 'pw-member', is_admin=False)
    token = user_store.create_session(uid, 'pytest')
    client = TestClient(create_app())
    client.cookies.set('pa_session', token)
    return client


def test_admin_can_list_and_create_users() -> None:
    client = authed_client()
    assert [u['username'] for u in client.get('/users/api/list').json()['users']] == ['tester']

    created = client.post('/users/api/create', json={'username': 'second', 'password': 'Password12!'})
    assert created.status_code == 200
    users = client.get('/users/api/list').json()['users']
    assert [u['username'] for u in users] == ['tester', 'second']
    assert users[1]['isAdmin'] is False


def test_create_validates_and_rejects_duplicates() -> None:
    client = authed_client()
    assert client.post('/users/api/create', json={'username': 'ab', 'password': 'Password12!'}).status_code == 400
    assert client.post('/users/api/create', json={'username': 'valid', 'password': 'short'}).status_code == 400
    client.post('/users/api/create', json={'username': 'dupe', 'password': 'Password12!'})
    assert client.post('/users/api/create', json={'username': 'dupe', 'password': 'Password12!'}).status_code == 409


def test_non_admins_are_refused() -> None:
    authed_client()
    member = _member_client()
    assert member.get('/users/api/list').status_code == 403
    assert member.post('/users/api/create', json={'username': 'x', 'password': 'Password12!'}).status_code == 403


def test_reset_password_signs_the_user_out() -> None:
    import time

    from phoenixadult.utils.auth.passwords import hash_token

    client = authed_client()
    uid = user_store.create_user('victim', 'old-password', is_admin=False)
    session = user_store.create_session(uid, 'pytest')

    assert client.post('/users/api/password', json={'id': uid, 'password': 'New-Password1'}).status_code == 200
    assert user_store.session_user(hash_token(session), time.time()) is None
    assert user_store.verify_login('victim', 'New-Password1') is not None


def test_the_last_admin_is_protected() -> None:
    client = authed_client()
    me = client.get('/users/api/list').json()['users'][0]
    assert client.post('/users/api/delete', json={'id': me['id']}).status_code == 409
    assert client.post('/users/api/admin', json={'id': me['id'], 'isAdmin': False}).status_code == 409

    other = client.post('/users/api/create', json={'username': 'second', 'password': 'Password12!', 'isAdmin': True}).json()['id']
    assert client.post('/users/api/admin', json={'id': other, 'isAdmin': False}).status_code == 200
    assert client.post('/users/api/admin', json={'id': other, 'isAdmin': True}).status_code == 200

    second = TestClient(create_app())
    second.cookies.set('pa_session', user_store.create_session(other, 'pytest'))
    assert second.post('/users/api/delete', json={'id': me['id']}).status_code == 200
    assert second.post('/users/api/admin', json={'id': other, 'isAdmin': False}).status_code == 409


def test_deleting_a_user_takes_their_connections() -> None:
    from phoenixadult.services import plex_connections

    client = authed_client()
    victim = client.post('/users/api/create', json={'username': 'victim', 'password': 'Password12!'}).json()['id']
    plex_connections.create(victim, 'Their Server')
    assert len(plex_connections.list_for_user(victim)) == 1

    assert client.post('/users/api/delete', json={'id': victim}).status_code == 200
    assert plex_connections.list_for_user(victim) == []


def test_unknown_user_is_404() -> None:
    client = authed_client()
    assert client.post('/users/api/delete', json={'id': 9999}).status_code == 404
    assert client.post('/users/api/password', json={'id': 9999, 'password': 'Password12!'}).status_code == 404
    assert client.post('/users/api/admin', json={'id': 9999, 'isAdmin': True}).status_code == 404
