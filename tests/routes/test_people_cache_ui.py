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
    assert 'People Image Cache' in page.text


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


def test_apostrophe_filename_renders_safe_buttons(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    from pathlib import Path

    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    monkeypatch.setenv('PEOPLE_CACHE_DIR', str(tmp_path))
    d = Path(str(tmp_path)) / 'actors' / 'female'
    d.mkdir(parents=True)
    (d / "actor.april-o'neil_female.jpg").write_bytes(b'x')

    page = TestClient(create_app()).get('/people-cache?token=tok')
    assert page.status_code == 200
    assert 'data-fn="actor.april-o&#x27;neil_female.jpg"' in page.text
    assert 'onclick="purge(' not in page.text
    assert 'onclick="restore(' not in page.text
    assert 'onclick="setGender(' not in page.text


def test_cards_are_hidden_until_the_tab_filter_runs(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    from pathlib import Path

    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    monkeypatch.setenv('PEOPLE_CACHE_DIR', str(tmp_path))
    d = Path(str(tmp_path)) / 'actors' / 'male'
    d.mkdir(parents=True)
    (d / 'actor.voodoo-child_male.jpg').write_bytes(b'x')

    page = TestClient(create_app()).get('/people-cache?token=tok')
    assert 'display:none}' in page.text.split('.card{')[1].split('\n')[0]
