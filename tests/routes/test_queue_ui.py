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
