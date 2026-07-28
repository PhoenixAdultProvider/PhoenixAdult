from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app


@pytest.fixture(autouse=True)
def _auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')


def test_requires_auth_and_serves_page_and_state() -> None:
    client = TestClient(create_app())
    assert client.get('/queue').status_code == 401
    page = client.get('/queue?token=tok')
    assert page.status_code == 200 and 'Scrape Queue' in page.text

    data = client.get('/queue/api/state', headers={'x-admin-token': 'tok'}).json()
    assert data['pending'] == 0 and data['entries'] == []
    assert any(p['tag'] == 'Nubiles:pace' for p in data['pacers'])
    for pacer in data['pacers']:
        assert {'tag', 'wait', 'gap', 'window_used', 'window_max', 'busy'} <= set(pacer)


def test_state_returns_at_once_when_the_watched_revision_is_stale() -> None:
    client = TestClient(create_app())
    headers = {'x-admin-token': 'tok'}
    revision = client.get('/queue/api/state', headers=headers).json()['revision']
    watched = client.get(f'/queue/api/state?wait=1&since={revision - 1}', headers=headers).json()
    assert watched['revision'] >= revision


def test_the_page_watches_instead_of_polling_on_a_timer() -> None:
    page = TestClient(create_app()).get('/queue?token=tok')
    assert 'wait=1&since=' in page.text
    assert 'async function watch()' in page.text
    assert 'setInterval(() => { if (!document.hidden) refresh(); }, 5000)' not in page.text
