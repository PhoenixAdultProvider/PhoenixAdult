from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app


def test_requires_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    client = TestClient(create_app())
    assert client.get('/people').status_code == 401
    page = client.get('/people?token=tok')
    assert page.status_code == 200
    assert 'People Cache' in page.text


def test_restore_requires_filename(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    client = TestClient(create_app())
    r = client.post('/people/restore', json={}, headers={'x-admin-token': 'tok'})
    assert r.status_code == 400


def test_gender_validates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    client = TestClient(create_app())
    hdr = {'x-admin-token': 'tok'}
    assert client.post('/people/gender', json={'gender': 'male'}, headers=hdr).status_code == 400
    assert client.post('/people/gender', json={'filename': 'a.jpg', 'gender': 'x'}, headers=hdr).status_code == 400
    r = client.post('/people/gender', json={'filename': 'unknown.jpg', 'gender': 'female'}, headers=hdr)
    assert r.status_code == 200 and r.json()['ok'] is False


def test_apostrophe_filename_renders_safe_buttons(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    from pathlib import Path

    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    monkeypatch.setenv('PEOPLE_CACHE_DIR', str(tmp_path))
    d = Path(str(tmp_path)) / 'actors' / 'female'
    d.mkdir(parents=True)
    (d / "actor.april-o'neil_female.jpg").write_bytes(b'x')

    page = TestClient(create_app()).get('/people?token=tok')
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

    page = TestClient(create_app()).get('/people?token=tok')
    assert 'display:none}' in page.text.split('.card{')[1].split('\n')[0]


def test_listing_is_built_from_the_index_tables(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    from pathlib import Path

    from phoenixadult.routes import people_cache_routes as pcr
    from phoenixadult.utils.images import face_crop_log

    monkeypatch.setenv('PEOPLE_CACHE_DIR', str(tmp_path))
    root = Path(str(tmp_path))
    d = root / 'actors' / 'female'
    d.mkdir(parents=True)
    (d / 'actor.jane-doe_female.jpg').write_bytes(b'x')
    (root / 'directors').mkdir()
    (root / 'directors' / 'director.greg-lansky.png').write_bytes(b'x')
    (root / 'originals').mkdir()
    (root / 'originals' / 'actor.jane-doe_female.webp').write_bytes(b'x')
    face_crop_log.record(
        str(d),
        name='Jane Doe',
        filename='actor.jane-doe_female.jpg',
        base='actor.jane-doe_female',
        orig_ext='.webp',
        upstream_url='https://up/j.webp',
        cropped=True,
    )

    entries = pcr._list_people(str(root))
    by_file = {e['filename']: e for e in entries}
    assert set(by_file) == {'actor.jane-doe_female.jpg', 'director.greg-lansky.png'}
    jane = by_file['actor.jane-doe_female.jpg']
    assert jane['relpath'] == 'actors/female/actor.jane-doe_female.jpg'
    assert jane['type'] == 'actors-female' and jane['role'] == 'actor' and jane['gender'] == 'female'
    assert jane['name'] == 'Jane Doe' and jane['cropped'] is True and jane['upstream_url'] == 'https://up/j.webp'
    assert jane['ts'] == face_crop_log.entry_for(str(d), 'actor.jane-doe_female.jpg')['ts'] and jane['mtime'] > 0  # type: ignore[index]
    greg = by_file['director.greg-lansky.png']
    assert greg['type'] == 'directors' and greg['name'] == 'Greg Lansky' and greg['cropped'] is False and greg['upstream_url'] == ''


def test_listing_falls_back_to_files_when_the_index_is_empty(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    from pathlib import Path

    from phoenixadult.routes import people_cache_routes as pcr
    from phoenixadult.utils import db
    from phoenixadult.utils.people import cache as pcache

    monkeypatch.setenv('PEOPLE_CACHE_DIR', str(tmp_path))
    d = Path(str(tmp_path)) / 'actors' / 'male'
    d.mkdir(parents=True)
    (d / 'actor.bob_male.jpg').write_bytes(b'x')

    db.connect()
    monkeypatch.setattr(pcache._index, '_key', (pcache.people_cache_dir(), pcache.env.state_db_path))
    entries = pcr._list_people(str(tmp_path))
    assert [e['relpath'] for e in entries] == ['actors/male/actor.bob_male.jpg']
    assert entries[0]['type'] == 'actors-male'


def test_cards_carry_cropped_flag_and_toggle_exists(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    from pathlib import Path

    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    monkeypatch.setenv('PEOPLE_CACHE_DIR', str(tmp_path))
    d = Path(str(tmp_path)) / 'actors' / 'female'
    d.mkdir(parents=True)
    (d / 'actor.jane-doe_female.jpg').write_bytes(b'x')

    page = TestClient(create_app()).get('/people?token=tok')
    assert 'data-cropped="0"' in page.text
    assert 'id="cropToggle"' in page.text
