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


def test_page_folds_tabs_and_filters_behind_one_toggle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    page = TestClient(create_app()).get('/people?token=tok')
    assert 'filtersToggle' in page.text
    assert 'body.filters-open .tabs' in page.text
    assert 'updateFiltersToggle()' in page.text
    assert '@media (max-width:720px)' in page.text


def test_people_page_offers_sfw_mode_and_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    page = TestClient(create_app()).get('/people?token=tok')
    assert 'id="sfwToggle"' in page.text
    assert 'id="resetBtn"' in page.text
    assert "const SFW_KEY = 'metadata-sfw';" in page.text
    assert 'function resetFilters()' in page.text
    assert 'body.sfw .imgs{display:none}' in page.text
    assert '::after' not in page.text


def test_people_images_are_not_fetched_until_hydrated(monkeypatch: pytest.MonkeyPatch) -> None:
    import re

    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    page = TestClient(create_app()).get('/people?token=tok')
    assert not re.search(r'<img [^>]*\ssrc=', page.text)
    assert 'img.dataset.src' in page.text


def test_resetting_people_filters_leaves_sfw_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    page = TestClient(create_app()).get('/people?token=tok')
    body = page.text[page.text.index('function resetFilters()') :]
    assert 'SFW' not in body[: body.index('showTab(curTab)')]


def _seed_scene(title: str, cur: str, studio: str, tagline: str, date: str, cast: list[str]) -> None:
    from phoenixadult.utils import cache as mc
    from phoenixadult.utils.cache import scene_store

    md: dict[str, object] = {
        'type': 'movie',
        'ratingKey': 'rk',
        'guid': 'g',
        'title': title,
        'studio': studio,
        'originallyAvailableAt': date,
        'Role': [{'tag': name} for name in cast],
    }
    if tagline:
        md['tagline'] = tagline
    scene_store.upsert(
        studio, cur, mc._hash(studio, cur), mc.bundle_path(mc._hash(studio, cur)), {'MediaContainer': {'identifier': 'i', 'size': 1, 'Metadata': [md]}}
    )


@pytest.fixture
def _person_cache(monkeypatch: pytest.MonkeyPatch, tmp_path):  # type: ignore[no-untyped-def]
    from pathlib import Path

    from phoenixadult.utils import db

    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    monkeypatch.setenv('STATE_DB_PATH', str(Path(str(tmp_path)) / 'state.db'))
    monkeypatch.setenv('PEOPLE_CACHE_DIR', str(Path(str(tmp_path)) / 'people'))
    monkeypatch.setenv('IMAGE_DIR', str(Path(str(tmp_path)) / 'images'))
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(Path(str(tmp_path)) / 'cache'))
    headshot = Path(str(tmp_path)) / 'people' / 'actors' / 'female' / 'actor.jane-doe_female.jpg'
    headshot.parent.mkdir(parents=True, exist_ok=True)
    headshot.write_bytes(b'\xff\xd8\xff\xdb' + b'0' * 64)
    yield
    db.close()


def test_the_edit_page_lists_the_scenes_that_credit_the_person(_person_cache: None) -> None:
    _seed_scene('Later Scene', 'c1', 'Brazzers', 'Baby Got Boobs', '2024-06-01', ['Jane Doe'])
    _seed_scene('Earlier Scene', 'c2', 'Vixen', '', '2023-01-05', ['Jane Doe', 'Someone Else'])
    _seed_scene('Not Hers', 'c3', 'Vixen', '', '2025-01-05', ['Someone Else'])

    page = TestClient(create_app()).get('/people/edit', params={'token': 'tok', 'filename': 'actor.jane-doe_female.jpg'})

    assert page.status_code == 200
    body = page.text
    assert '<legend>Scenes</legend>' in body
    assert body.index('Later Scene') < body.index('Earlier Scene')
    assert 'Not Hers' not in body
    assert 'Baby Got Boobs' in body and 'Brazzers' in body and '2024-06-01' in body
    assert 'href="/metadata/edit?key=scenes/' in body and 'token=tok' in body


def test_the_edit_page_says_so_when_no_snapshot_credits_the_person(_person_cache: None) -> None:
    _seed_scene('Not Hers', 'c9', 'Vixen', '', '2025-01-05', ['Someone Else'])

    body = TestClient(create_app()).get('/people/edit', params={'token': 'tok', 'filename': 'actor.jane-doe_female.jpg'}).text

    assert 'No cached snapshot credits this person.' in body


def test_the_scene_list_is_skipped_when_the_cache_is_off(_person_cache: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'false')

    body = TestClient(create_app()).get('/people/edit', params={'token': 'tok', 'filename': 'actor.jane-doe_female.jpg'}).text

    assert 'The snapshot cache is off' in body
