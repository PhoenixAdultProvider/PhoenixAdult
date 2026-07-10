from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.app_factory import create_app


def test_requires_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    client = TestClient(create_app())
    assert client.get('/metadata-cache').status_code == 401
    page = client.get('/metadata-cache?token=tok')
    assert page.status_code == 200
    assert 'Snapshot Metadata Cache' in page.text


def test_purge_validates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    client = TestClient(create_app())
    hdr = {'x-admin-token': 'tok'}
    assert client.post('/metadata-cache/purge', json={}, headers=hdr).status_code == 400
    r = client.post('/metadata-cache/purge', json={'key': 'nope/abc'}, headers=hdr)
    assert r.status_code == 200 and r.json()['ok'] is False
