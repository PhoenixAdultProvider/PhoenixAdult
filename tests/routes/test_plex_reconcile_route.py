from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from phoenixadult.services import plex_reconcile
from tests.conftest import authed_client, seed_connection

BASE = 'http://192.0.2.10:32400'


@pytest.fixture(autouse=True)
def _fresh_progress() -> None:
    plex_reconcile._progress.clear()


def test_requires_auth() -> None:
    assert TestClient(create_app()).get('/plex/status', headers={'accept': 'application/json'}).status_code == 401


def test_status_counts_configured_connections() -> None:
    client = authed_client()
    assert client.get('/plex/status').json() == {'enabled': False, 'connections': 0}
    seed_connection(url=BASE)
    assert client.get('/plex/status').json() == {'enabled': True, 'connections': 1}


def test_connections_crud() -> None:
    client = authed_client()
    created = client.post('/plex/connections', json={'name': 'Home'})
    assert created.status_code == 200
    cid = created.json()['id']

    listed = client.get('/plex/connections').json()['connections']
    assert [c['name'] for c in listed] == ['Home']
    assert listed[0]['hasToken'] is False

    updated = client.post(f'/plex/connections/{cid}', json={'serverUrl': BASE, 'allowedClients': ['abc123']})
    assert updated.json()['serverUrl'] == BASE
    assert updated.json()['allowedClients'] == ['abc123']

    assert client.post('/plex/connections', json={'name': 'Home'}).status_code == 409
    assert client.post('/plex/connections', json={'name': ''}).status_code == 400

    assert client.post(f'/plex/connections/{cid}/delete').status_code == 200
    assert client.get('/plex/connections').json()['connections'] == []


def test_token_is_write_only() -> None:
    client = authed_client()
    cid = client.post('/plex/connections', json={'name': 'Home'}).json()['id']
    assert client.post(f'/plex/connections/{cid}/token', json={'token': 'secret-token'}).status_code == 200
    body = client.get('/plex/connections').text
    assert 'secret-token' not in body
    assert client.get('/plex/connections').json()['connections'][0]['hasToken'] is True


def test_another_users_connection_is_not_visible() -> None:
    from phoenixadult.utils.auth import user_store

    owner = authed_client()
    cid = owner.post('/plex/connections', json={'name': 'Mine'}).json()['id']

    other_id = user_store.create_user('intruder', 'pw-intruder', is_admin=True)
    token = user_store.create_session(other_id, 'pytest')
    intruder = TestClient(create_app())
    intruder.cookies.set('pa_session', token)

    assert intruder.get('/plex/connections').json()['connections'] == []
    assert intruder.post(f'/plex/connections/{cid}', json={'name': 'Stolen'}).status_code == 404
    assert intruder.post(f'/plex/connections/{cid}/delete').status_code == 404
    assert intruder.get(f'/plex/connections/{cid}/update').status_code == 404


def test_actions_409_until_the_connection_is_configured() -> None:
    client = authed_client()
    cid = client.post('/plex/connections', json={'name': 'Bare'}).json()['id']
    assert client.post(f'/plex/connections/{cid}/reconcile').status_code == 409
    assert client.get(f'/plex/connections/{cid}/libraries').status_code == 409
    assert client.post(f'/plex/connections/{cid}/import?section=1').status_code == 409


def test_reconcile_progress_is_per_connection() -> None:
    client = authed_client()
    connection = seed_connection(url=BASE)
    body = client.get(f'/plex/connections/{connection.id}/reconcile/progress').json()
    assert body == {'active': False, 'total': 0, 'inspected': 0}
    assert client.get('/plex/connections/9999/reconcile/progress').status_code == 404


def test_reconcile_rejects_a_bad_limit() -> None:
    client = authed_client()
    connection = seed_connection(url=BASE)
    assert client.post(f'/plex/connections/{connection.id}/reconcile?limit=abc').status_code == 400
