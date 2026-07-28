from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from phoenixadult.utils import db
from scripts.rename_studio import migrate


@pytest.fixture(autouse=True)
def _tmp_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    monkeypatch.setenv('STATE_DB_PATH', str(tmp_path / 'state.db'))
    yield tmp_path
    db.close()


def test_rename_merges_dimensions_and_leaves_snapshot_paths_alone(_tmp_db: Path) -> None:
    conn = db.connect()
    with conn:
        conn.execute("INSERT INTO studios(name) VALUES('Old Name'), ('Other')")
        conn.execute("INSERT INTO collections(name) VALUES('Old Name'), ('New Name')")
        sid = conn.execute("SELECT id FROM studios WHERE name='Old Name'").fetchone()['id']
        conn.execute(
            'INSERT INTO scenes(hash, site, cur_id, rel_path, identifier, rating_key, guid, title, studio_id, updated_at)'
            " VALUES('h1','s','c','scenes/h1/h1','i','rk','g','T',?,0)",
            (sid,),
        )
        scene = conn.execute('SELECT id FROM scenes').fetchone()['id']
        cid = conn.execute("SELECT id FROM collections WHERE name='Old Name'").fetchone()['id']
        conn.execute('INSERT INTO scene_collections(scene_id, collection_id, pos) VALUES(?,?,0)', (scene, cid))
        conn.execute(
            'INSERT INTO scene_images(scene_id, kind, rel_path, width, height, bytes, pos) VALUES(?,?,?,?,?,?,?)',
            (scene, 'coverPoster', '/cache/scenes/h1/h1/images/p.jpg', 100, 100, 5, 0),
        )

    assert migrate('Old Name', 'New Name') == 2

    assert sorted(r['name'] for r in conn.execute('SELECT name FROM studios')) == ['New Name', 'Other']
    assert conn.execute('SELECT rel_path FROM scenes').fetchone()['rel_path'] == 'scenes/h1/h1'
    assert conn.execute('SELECT rel_path FROM scene_images').fetchone()['rel_path'] == '/cache/scenes/h1/h1/images/p.jpg'
    assert [r['name'] for r in conn.execute('SELECT name FROM collections')] == ['New Name']
    assert conn.execute('SELECT COUNT(*) c FROM scene_collections').fetchone()['c'] == 1


def test_rename_can_recase_a_name_in_place(_tmp_db: Path) -> None:
    conn = db.connect()
    with conn:
        conn.execute("INSERT INTO people(name) VALUES('Gi Joey')")

    assert migrate('gi joey', 'GI Joey', ['people']) == 1

    assert [r['name'] for r in conn.execute('SELECT name FROM people')] == ['GI Joey']


def test_rename_merges_into_an_existing_row_of_another_table(_tmp_db: Path) -> None:
    conn = db.connect()
    with conn:
        conn.execute("INSERT INTO genres(name) VALUES('Old Genre'), ('New Genre')")
        conn.execute(
            'INSERT INTO scenes(hash, site, cur_id, rel_path, identifier, rating_key, guid, title, updated_at)'
            " VALUES('h2','s','c','scenes/h2/h2','i','rk','g','T',0)"
        )
        scene = int(conn.execute('SELECT id FROM scenes').fetchone()['id'])
        old = int(conn.execute("SELECT id FROM genres WHERE name='Old Genre'").fetchone()['id'])
        conn.execute('INSERT INTO scene_genres(scene_id, genre_id, pos) VALUES(?,?,0)', (scene, old))

    assert migrate('Old Genre', 'New Genre', ['genres']) == 1

    assert [r['name'] for r in conn.execute('SELECT name FROM genres')] == ['New Genre']
    new = int(conn.execute("SELECT id FROM genres WHERE name='New Genre'").fetchone()['id'])
    assert int(conn.execute('SELECT genre_id FROM scene_genres').fetchone()['genre_id']) == new
