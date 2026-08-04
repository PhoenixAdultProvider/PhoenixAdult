from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import httpx
import pytest
import respx

from phoenixadult.utils import db
from phoenixadult.utils.images import face_crop_log
from phoenixadult.utils.people import cache
from phoenixadult.utils.people.generic import generic_image_url
from phoenixadult.utils.people.image_source import source_for_url


@pytest.mark.parametrize(
    ('url', 'expected'),
    [
        ('https://www.iafd.com/graphics/headshots/jane.jpg', 'IAFD'),
        ('https://imgs1cdn.adultempire.com/actors/123h.jpg', 'AdultDVDEmpire'),
        ('https://img.indexxx.com/images/thumbs/jane.jpg', 'Indexxx'),
        ('https://www.babepedia.com/pics/Jane%20Doe.jpg', 'Babepedia'),
        ('http://www.babesandstars.com/j/jane-doe/pic.jpg', 'Babes and Stars'),
        ('http://www.boobpedia.com/images/jane.jpg', 'Boobpedia'),
        ('https://www.javdatabase.com/idolimages/full/jane.webp', 'JAVDatabase'),
        ('https://www.javbus.com/pics/actress/a1.jpg', 'JAVBus'),
        ('https://images.freeones.com/jane/bio.jpg', 'Freeones'),
        ('https://cdn.somestudio.com/scenes/actor.jpg', ''),
        ('', ''),
    ],
)
def test_source_is_derived_from_the_image_host(url: str, expected: str) -> None:
    assert source_for_url(url) == expected


def test_the_silhouette_is_its_own_source() -> None:
    assert source_for_url(generic_image_url('female')) == 'Generic'


@respx.mock
async def test_caching_records_the_source_it_came_from(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('IMAGE_DIR', str(tmp_path))
    monkeypatch.setenv('PEOPLE_CACHE_REPLACE_ENABLE', 'true')
    url = 'https://img.indexxx.com/images/thumbs/jane.jpg'
    respx.get(url).mock(return_value=httpx.Response(200, content=b'BYTES', headers={'content-type': 'image/jpeg'}))

    assert await cache.cache_photo(url, 'Jane Doe', 'actor', 'female') is not None

    entry = face_crop_log.entry_for(str(tmp_path / 'people' / 'actors' / 'female'), 'actor.jane-doe_female.jpg')
    assert entry is not None and entry['source'] == 'Indexxx'


@respx.mock
async def test_an_explicit_source_beats_the_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('IMAGE_DIR', str(tmp_path))
    monkeypatch.setenv('PEOPLE_CACHE_REPLACE_ENABLE', 'true')
    url = 'https://cdn.somestudio.com/scenes/jane.jpg'
    respx.get(url).mock(return_value=httpx.Response(200, content=b'BYTES', headers={'content-type': 'image/jpeg'}))

    assert await cache.cache_photo(url, 'Jane Doe', 'actor', 'female', source='Scene') is not None

    entry = face_crop_log.entry_for(str(tmp_path / 'people' / 'actors' / 'female'), 'actor.jane-doe_female.jpg')
    assert entry is not None and entry['source'] == 'Scene'


def _legacy_db(path: Path, rows: list[tuple[str, str]]) -> None:
    conn = sqlite3.connect(path)
    for idx, script in enumerate(db._MIGRATIONS[:4], start=1):
        assert isinstance(script, str)
        conn.executescript(script)
        conn.execute(f'PRAGMA user_version = {idx}')
    for rel_path, url in rows:
        entry = {'name': 'Jane Doe', 'filename': rel_path.rpartition('/')[2], 'base': 'b', 'orig_ext': '.jpg', 'upstream_url': url, 'cropped': False}
        conn.execute('INSERT INTO crop_log(rel_path, entry, cropped_at) VALUES(?, ?, ?)', (rel_path, json.dumps(entry), time.time()))
    conn.commit()
    conn.close()


def test_existing_headshots_get_a_source_derived_from_their_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / 'legacy.db'
    _legacy_db(
        path,
        [
            ('actors/female/actor.jane_female.jpg', 'https://www.iafd.com/graphics/headshots/jane.jpg'),
            ('actors/male/actor.john_male.jpg', 'https://cdn.somestudio.com/scenes/john.jpg'),
            ('actors/female/actor.jill_female.jpg', ''),
        ],
    )
    monkeypatch.setenv('STATE_DB_PATH', str(path))
    db.close()

    conn = db.connect()
    sources = {str(r['rel_path']): str(r['source']) for r in conn.execute('SELECT rel_path, source FROM crop_log').fetchall()}
    assert sources['actors/female/actor.jane_female.jpg'] == 'IAFD'
    assert sources['actors/male/actor.john_male.jpg'] == 'Scene'
    assert sources['actors/female/actor.jill_female.jpg'] == ''
