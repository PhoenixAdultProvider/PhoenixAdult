from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from tests.conftest import authed_cookies


@pytest.fixture
def client() -> TestClient:
    c = TestClient(create_app())
    c.cookies.update(authed_cookies())
    return c


def test_requires_auth_and_serves_page_and_state(client: TestClient) -> None:
    assert TestClient(create_app()).get('/queue', headers={'accept': 'application/json'}).status_code == 401
    page = client.get('/queue')
    assert page.status_code == 200 and 'Scrape Queue' in page.text

    data = client.get('/queue/api/state').json()
    assert data['pending'] == 0 and data['entries'] == []
    assert any(p['tag'] == 'Nubiles:pace' for p in data['pacers'])
    for pacer in data['pacers']:
        assert {'tag', 'wait', 'gap', 'window_used', 'window_max', 'busy'} <= set(pacer)
    assert data['fastLane'] == {'busy': 0, 'slots': 5, 'waiting': 0}


def test_state_returns_at_once_when_the_watched_revision_is_stale(client: TestClient) -> None:
    revision = client.get('/queue/api/state').json()['revision']
    watched = client.get(f'/queue/api/state?wait=1&since={revision - 1}').json()
    assert watched['revision'] >= revision


def test_the_page_watches_instead_of_polling_on_a_timer(client: TestClient) -> None:
    page = client.get('/queue')
    assert 'wait=1&since=' in page.text
    assert 'async function watch()' in page.text
    assert 'setInterval(() => { if (!document.hidden) refresh(); }, 5000)' not in page.text


def test_admins_can_pause_and_resume_one_queue() -> None:
    from tests.conftest import authed_client

    client = authed_client()
    r = client.post('/queue/api/pause', json={'kind': 'search'})
    assert r.status_code == 200 and r.json()['pausedKinds'] == ['search']
    body = client.get('/queue').text
    assert 'id="pause-search"' in body and 'togglePause(' in body
    r = client.post('/queue/api/resume', json={'kind': 'search'})
    assert r.status_code == 200 and r.json()['pausedKinds'] == []
    assert client.post('/queue/api/pause', json={'kind': 'nope'}).status_code == 400


def test_a_bare_resume_still_lifts_the_global_pause() -> None:
    from phoenixadult.services import scrape_queue
    from tests.conftest import authed_client

    scrape_queue.pause('test pause', 500)
    client = authed_client()
    assert client.post('/queue/api/resume', json={}).status_code == 200
    assert scrape_queue.paused_for() == 0


def test_admins_can_remove_a_single_queued_job() -> None:
    from tests.conftest import authed_client

    client = authed_client()
    assert client.post('/queue/api/remove', json={'key': 'not-there'}).status_code == 404
    assert client.post('/queue/api/remove', json={}).status_code == 400
    body = client.get('/queue').text
    assert 'item-x' in body and "post('/queue/api/remove'" in body
