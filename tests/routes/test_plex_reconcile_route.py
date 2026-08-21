from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from phoenixadult.services import plex_reconcile
from tests.support import authed_client, seed_connection

BASE = 'http://192.0.2.10:32400'


@pytest.fixture(autouse=True)
def _fresh_progress() -> None:
    from phoenixadult.services import plex_jobs

    plex_reconcile._progress.clear()
    plex_jobs.reset()


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


def test_a_running_job_is_refused_and_queryable_across_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    from phoenixadult.services import plex_jobs

    client = authed_client()
    connection = seed_connection(name='Home', url=BASE, token='t')

    plex_jobs._jobs[(connection.id, 'reconcile')] = {
        'active': True,
        'phase': 'inspecting',
        'total': 8,
        'done': 3,
        'report': None,
        'error': None,
        'startedAt': time.time(),
        'finishedAt': None,
    }

    assert client.post(f'/plex/connections/{connection.id}/reconcile').status_code == 409, 'no duplicate launch while active'

    jobs = client.get(f'/plex/connections/{connection.id}/jobs').json()['jobs']
    assert jobs['reconcile'] == {
        'active': True,
        'phase': 'inspecting',
        'total': 8,
        'done': 3,
        'report': None,
        'error': None,
        'startedAt': jobs['reconcile']['startedAt'],
        'finishedAt': None,
    }


def test_a_finished_job_retains_its_report_for_the_returning_page() -> None:
    import time

    from phoenixadult.services import plex_jobs

    client = authed_client()
    connection = seed_connection(name='Home', url=BASE, token='t')
    plex_jobs._jobs[(connection.id, 'import')] = {
        'active': False,
        'phase': 'done',
        'total': 0,
        'done': 0,
        'report': {'applied': True, 'imported': 5, 'scanned': 9},
        'error': None,
        'startedAt': time.time() - 5,
        'finishedAt': time.time(),
    }
    job = client.get(f'/plex/connections/{connection.id}/jobs').json()['jobs']['import']
    assert job['active'] is False and job['report']['imported'] == 5, 'the report is still there when the page comes back'


def test_stale_finished_jobs_drop_out_of_the_status() -> None:
    import time

    from phoenixadult.services import plex_jobs

    client = authed_client()
    connection = seed_connection(name='Home', url=BASE, token='t')
    plex_jobs._jobs[(connection.id, 'reconcile')] = {
        'active': False,
        'phase': 'done',
        'total': 0,
        'done': 0,
        'report': {'x': 1},
        'error': None,
        'startedAt': 0,
        'finishedAt': time.time() - (31 * 60),
    }
    assert client.get(f'/plex/connections/{connection.id}/jobs').json()['jobs'] == {}, 'a run from an hour ago no longer resurfaces'


def test_jobs_endpoint_is_owner_scoped() -> None:
    client = authed_client()
    connection = seed_connection(name='Home', url=BASE, token='t')
    assert client.get(f'/plex/connections/{connection.id}/jobs').json() == {'jobs': {}}
    assert client.get('/plex/connections/9999/jobs').status_code == 404


def test_import_item_route_imports_one_scene(monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.routes import plex_routes
    from phoenixadult.services.plex_import import ItemReport

    async def _fake(connection: object, token: str, rating_key: str, overwrite: bool = False) -> ItemReport:
        return ItemReport(rating_key=rating_key, title='One Scene', status='imported', site='Fit18', cur_id='abc', detail='4 images')

    monkeypatch.setattr(plex_routes.plex_import, 'import_item', _fake)
    client = authed_client()
    connection = seed_connection(url=BASE)

    assert client.post(f'/plex/connections/{connection.id}/import-item').status_code == 400
    body = client.post(f'/plex/connections/{connection.id}/import-item?ratingKey=42').json()
    assert body['item']['status'] == 'imported'
    assert body['item']['ratingKey'] == '42'
    assert body['item']['detail'] == '4 images'


def test_import_item_route_requires_a_configured_connection() -> None:
    client = authed_client()
    cid = client.post('/plex/connections', json={'name': 'Bare'}).json()['id']
    assert client.post(f'/plex/connections/{cid}/import-item?ratingKey=1').status_code == 409
