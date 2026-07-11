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


def test_page_injects_duplicate_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    import app.routes.metadata_cache_routes as mcr

    monkeypatch.setattr(mcr.metadata_cache, 'duplicate_entries', lambda: ['a/b/c', 'd/e/f'])
    monkeypatch.setattr(mcr.metadata_cache, 'entries', lambda: [])
    page = TestClient(create_app()).get('/metadata-cache?token=tok')
    assert 'const DUP_KEYS = ["a/b/c", "d/e/f"];' in page.text
    assert 'Show Duplicates' in page.text
