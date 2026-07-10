from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.app_factory import create_app


def test_requires_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    client = TestClient(create_app())
    assert client.get('/people-cache').status_code == 401
    page = client.get('/people-cache?token=tok')
    assert page.status_code == 200
    assert 'People image cache' in page.text


def test_restore_requires_filename(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    client = TestClient(create_app())
    r = client.post('/people-cache/restore', json={}, headers={'x-admin-token': 'tok'})
    assert r.status_code == 400


def test_gender_validates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    client = TestClient(create_app())
    hdr = {'x-admin-token': 'tok'}
    assert client.post('/people-cache/gender', json={'gender': 'male'}, headers=hdr).status_code == 400
    assert client.post('/people-cache/gender', json={'filename': 'a.jpg', 'gender': 'x'}, headers=hdr).status_code == 400
    r = client.post('/people-cache/gender', json={'filename': 'unknown.jpg', 'gender': 'female'}, headers=hdr)
    assert r.status_code == 200 and r.json()['ok'] is False
