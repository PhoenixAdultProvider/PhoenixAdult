from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from app.utils import db
from scripts.rename_studio import migrate


@pytest.fixture(autouse=True)
def _tmp_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    monkeypatch.setenv('STATE_DB_PATH', str(tmp_path / 'state.db'))
    yield tmp_path
    db.close()


def test_rename_merges_dimensions_paths_and_folders(_tmp_db: Path) -> None:
    conn = db.connect()
    with conn:
        conn.execute("INSERT INTO studios(name) VALUES('Old Name'), ('Other')")
        conn.execute("INSERT INTO collections(name) VALUES('Old Name'), ('New Name')")
        sid = conn.execute("SELECT id FROM studios WHERE name='Old Name'").fetchone()['id']
        conn.execute(
            'INSERT INTO scenes(hash, site, cur_id, rel_path, identifier, rating_key, guid, title, studio_id, updated_at)'
            " VALUES('h1','s','c','net/old-name/h1','i','rk','g','T',?,0)",
            (sid,),
        )
        scene = conn.execute('SELECT id FROM scenes').fetchone()['id']
        cid = conn.execute("SELECT id FROM collections WHERE name='Old Name'").fetchone()['id']
        conn.execute('INSERT INTO scene_collections(scene_id, collection_id, pos) VALUES(?,?,0)', (scene, cid))
        conn.execute(
            'INSERT INTO scene_images(scene_id, kind, rel_path, width, height, bytes, pos) VALUES(?,?,?,?,?,?,?)',
            (scene, 'coverPoster', 'net/old-name/h1/images/p.jpg', 100, 100, 5, 0),
        )
    img = _tmp_db / 'cache' / 'net' / 'old-name' / 'h1' / 'images' / 'p.jpg'
    img.parent.mkdir(parents=True)
    img.write_bytes(b'x')

    dims, dirs, paths = migrate(_tmp_db / 'cache', 'Old Name', 'New Name')

    assert (dims, dirs, paths) == (2, 1, 2)
    assert sorted(r['name'] for r in conn.execute('SELECT name FROM studios')) == ['New Name', 'Other']
    assert conn.execute('SELECT rel_path FROM scenes').fetchone()['rel_path'] == 'net/new-name/h1'
    assert conn.execute('SELECT rel_path FROM scene_images').fetchone()['rel_path'] == 'net/new-name/h1/images/p.jpg'
    assert [r['name'] for r in conn.execute('SELECT name FROM collections')] == ['New Name']
    assert conn.execute('SELECT COUNT(*) c FROM scene_collections').fetchone()['c'] == 1
    assert (_tmp_db / 'cache' / 'net' / 'new-name' / 'h1' / 'images' / 'p.jpg').exists()
    assert not (_tmp_db / 'cache' / 'net' / 'old-name').exists()
