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
    assert data['fastLane'] == {'busy': 0, 'slots': 3, 'waiting': 0}


def test_state_returns_at_once_when_the_watched_revision_is_stale(client: TestClient) -> None:
    revision = client.get('/queue/api/state').json()['revision']
    watched = client.get(f'/queue/api/state?wait=1&since={revision - 1}').json()
    assert watched['revision'] >= revision


def test_the_page_watches_instead_of_polling_on_a_timer(client: TestClient) -> None:
    page = client.get('/queue')
    assert 'wait=1&since=' in page.text
    assert 'async function watch()' in page.text
    assert 'setInterval(() => { if (!document.hidden) refresh(); }, 5000)' not in page.text
