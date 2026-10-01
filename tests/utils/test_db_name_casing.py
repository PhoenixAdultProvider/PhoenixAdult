from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from phoenixadult.utils import db


@pytest.fixture(autouse=True)
def _tmp_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setenv('STATE_DB_PATH', str(tmp_path / 'state.db'))
    yield
    db.close()


def _person(conn: sqlite3.Connection, name: str) -> int:
    from phoenixadult.utils.cache.scene_store import _person_id

    return _person_id(conn, name, None, '')


def test_a_differently_cased_name_reuses_the_existing_row() -> None:
    conn = db.connect()
    with conn:
        first = db.dim_id(conn, 'genres', 'Anal')
        again = db.dim_id(conn, 'genres', 'ANAL')
        lower = db.dim_id(conn, 'genres', 'anal')

    assert first == again == lower
    assert [r['name'] for r in conn.execute('SELECT name FROM genres')] == ['Anal']


def test_the_stored_spelling_is_never_rewritten_by_a_later_scrape() -> None:
    conn = db.connect()
    with conn:
        db.dim_id(conn, 'collections', 'Mckenna Lynn')
        db.dim_id(conn, 'collections', 'McKenna Lynn')

    assert [r['name'] for r in conn.execute('SELECT name FROM collections')] == ['Mckenna Lynn']


def test_people_match_case_insensitively_in_and_out_of_scope() -> None:
    conn = db.connect()
    with conn:
        studio = db.dim_id(conn, 'studios', 'Brazzers')
        first = _person(conn, 'Mackenzie Mace')
        again = _person(conn, 'MacKenzie Mace')
        scoped = db.dim_id(conn, 'people', 'Someone Else')
        conn.execute('UPDATE people SET scope_studio_id = ? WHERE id = ?', (studio, scoped))
        rescoped = conn.execute('SELECT id FROM people WHERE name = ? COLLATE NOCASE AND scope_studio_id = ?', ('SOMEONE ELSE', studio)).fetchone()

    assert first == again
    assert rescoped is not None and int(rescoped['id']) == scoped
    assert [r['name'] for r in conn.execute('SELECT name FROM people ORDER BY id')] == ['Mackenzie Mace', 'Someone Else']


@pytest.mark.parametrize('table', ['people', 'studios', 'taglines', 'collections', 'genres', 'countries'])
def test_the_database_refuses_a_second_spelling(table: str) -> None:
    conn = db.connect()
    with conn:
        conn.execute(f'INSERT INTO {table}(name) VALUES(?)', ('Case Test',))  # noqa: S608 - fixed table names

    with pytest.raises(sqlite3.IntegrityError), conn:
        conn.execute(f'INSERT INTO {table}(name) VALUES(?)', ('CASE TEST',))  # noqa: S608


def test_merging_a_studio_never_deletes_its_scenes() -> None:
    conn = db.connect()
    with conn:
        keep = db.dim_id(conn, 'studios', 'Keeper')
        drop = db.dim_id(conn, 'studios', 'Doomed')
        conn.execute(
            'INSERT INTO scenes(hash, site, cur_id, rel_path, identifier, rating_key, guid, title, studio_id, updated_at)'
            " VALUES('h','s','c','scenes/h/h','i','rk','g','T',?,0)",
            (drop,),
        )

    with conn:
        db.merge_name_row(conn, 'studios', int(keep or 0), int(drop or 0))

    row = conn.execute('SELECT studio_id FROM scenes').fetchone()
    assert row is not None and int(row['studio_id']) == keep
    assert [r['name'] for r in conn.execute('SELECT name FROM studios')] == ['Keeper']


def test_pruning_drops_unreferenced_names_and_keeps_credited_ones() -> None:
    conn = db.connect()
    with conn:
        kept = db.dim_id(conn, 'genres', 'Anal')
        db.dim_id(conn, 'genres', 'Orphaned Tag')
        db.dim_id(conn, 'collections', 'Nobody Uses This')
        studio = db.dim_id(conn, 'studios', 'Brazzers')
        conn.execute(
            'INSERT INTO scenes(hash, site, cur_id, rel_path, identifier, rating_key, guid, title, studio_id, updated_at)'
            " VALUES('h','s','c','scenes/h/h','i','rk','g','T',?,0)",
            (studio,),
        )
        scene = int(conn.execute('SELECT id FROM scenes').fetchone()['id'])
        conn.execute('INSERT INTO scene_genres(scene_id, genre_id, pos) VALUES(?,?,0)', (scene, kept))

    with conn:
        pruned = db.prune_orphan_names(conn)

    assert pruned == {'genres': 1, 'collections': 1}
    assert [str(r['name']) for r in conn.execute('SELECT name FROM genres')] == ['Anal']
    assert conn.execute('SELECT COUNT(*) c FROM collections').fetchone()['c'] == 0
    assert [str(r['name']) for r in conn.execute('SELECT name FROM studios')] == ['Brazzers']
    assert conn.execute('SELECT COUNT(*) c FROM scenes').fetchone()['c'] == 1
