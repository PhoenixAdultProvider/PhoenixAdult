from __future__ import annotations

from pathlib import Path

import pytest

from phoenixadult.utils import db
from phoenixadult.utils.images import face_crop_log
from phoenixadult.utils.people import cache


@pytest.fixture(autouse=True)
def _cache_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv('PEOPLE_CACHE_ENABLE', 'true')
    monkeypatch.setenv('IMAGE_DIR', str(tmp_path))
    return tmp_path / 'people'


def _seed(root: Path, rel: str, data: bytes = b'img') -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def test_reconcile_builds_index_from_files(_cache_dir: Path) -> None:
    _seed(_cache_dir, 'actors/female/actor.jane-doe_female.jpg')
    _seed(_cache_dir, 'directors/director.john-smith.png')
    _seed(_cache_dir, 'originals/actor.jane-doe_female.webp')

    hit = cache.lookup_cached('Jane Doe', 'actor')
    assert hit is not None and hit['gender'] == 'female'
    assert '/images/local/actors/female/actor.jane-doe_female.jpg' in hit['served_url']
    assert cache.lookup_cached('John Smith', 'director') is not None

    rows = db.connect().execute('SELECT rel_path FROM people_images ORDER BY rel_path').fetchall()
    assert [r['rel_path'] for r in rows] == ['actors/female/actor.jane-doe_female.jpg', 'directors/director.john-smith.png']


def test_index_rebuilds_after_db_loss(_cache_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _seed(_cache_dir, 'actors/male/actor.bob_male.jpg')
    assert cache.lookup_cached('Bob', 'actor') is not None

    db.close()
    monkeypatch.setenv('STATE_DB_PATH', str(tmp_path / 'state2.db'))
    hit = cache.lookup_cached('Bob', 'actor')
    assert hit is not None and hit['gender'] == 'male'


def test_scan_on_miss_picks_up_manual_drop(_cache_dir: Path) -> None:
    _cache_dir.mkdir(parents=True, exist_ok=True)
    assert cache.lookup_cached('Jane Doe', 'actor') is None

    _seed(_cache_dir, 'actors/unknown/actor.jane-doe.jpg')
    hit = cache.lookup_cached('Jane Doe', 'actor')
    assert hit is not None and hit['gender'] == ''
    row = db.connect().execute('SELECT rel_path FROM people_images').fetchone()
    assert row['rel_path'] == 'actors/unknown/actor.jane-doe.jpg'


def test_stale_row_healed_on_lookup(_cache_dir: Path) -> None:
    f = _seed(_cache_dir, 'actors/female/actor.jane-doe_female.jpg')
    assert cache.lookup_cached('Jane Doe', 'actor') is not None

    f.unlink()
    assert cache.lookup_cached('Jane Doe', 'actor') is None
    assert db.connect().execute('SELECT COUNT(*) AS c FROM people_images').fetchone()['c'] == 0


def test_crop_log_round_trip(_cache_dir: Path) -> None:
    sub = _cache_dir / 'actors' / 'female'
    sub.mkdir(parents=True)
    face_crop_log.record(
        str(sub),
        name='Jane Doe',
        filename='actor.jane-doe_female.jpg',
        base='actor.jane-doe_female',
        orig_ext='.webp',
        upstream_url='https://cdn.example/jane.webp',
        cropped=True,
    )

    entries = face_crop_log.recent(str(sub))
    assert entries and entries[0]['filename'] == 'actor.jane-doe_female.jpg' and entries[0]['cropped'] is True
