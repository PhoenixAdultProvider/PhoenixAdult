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


def test_folding_keeps_the_referenced_row_and_moves_its_credits() -> None:
    conn = db.connect()
    with conn:
        conn.execute('DROP INDEX genres_ci')
        keep = db.dim_id(conn, 'genres', 'Baeb')
        conn.execute("INSERT INTO genres(name) VALUES('BAEB')")
        drop = int(conn.execute("SELECT id FROM genres WHERE name = 'BAEB'").fetchone()['id'])
        conn.execute(
            'INSERT INTO scenes(hash, site, cur_id, rel_path, identifier, rating_key, guid, title, updated_at)'
            " VALUES('h','s','c','scenes/h/h','i','rk','g','T',0)"
        )
        scene = int(conn.execute('SELECT id FROM scenes').fetchone()['id'])
        conn.execute('INSERT INTO scene_genres(scene_id, genre_id, pos) VALUES(?,?,0)', (scene, drop))

    with conn:
        db._fold_case_duplicate_names(conn)

    names = [r['name'] for r in conn.execute('SELECT name FROM genres')]
    assert names == ['BAEB']
    assert int(conn.execute('SELECT genre_id FROM scene_genres').fetchone()['genre_id']) == drop
    assert conn.execute('SELECT 1 FROM genres WHERE id = ?', (keep,)).fetchone() is None


def test_folding_keeps_the_first_row_when_both_are_used() -> None:
    conn = db.connect()
    with conn:
        conn.execute('DROP INDEX people_ci_global')
        conn.execute("INSERT INTO people(name) VALUES('Mckenna Lynn'), ('McKenna Lynn')")
        first, second = (int(r['id']) for r in conn.execute('SELECT id FROM people ORDER BY id'))
        conn.execute(
            'INSERT INTO scenes(hash, site, cur_id, rel_path, identifier, rating_key, guid, title, updated_at)'
            " VALUES('h','s','c','scenes/h/h','i','rk','g','T',0)"
        )
        scene = int(conn.execute('SELECT id FROM scenes').fetchone()['id'])
        conn.executemany(
            'INSERT INTO scene_people(scene_id, person_id, role, pos) VALUES(?,?,?,?)',
            [(scene, first, 'actor', 0), (scene, second, 'director', 1)],
        )

    with conn:
        db._fold_case_duplicate_names(conn)

    assert [r['name'] for r in conn.execute('SELECT name FROM people')] == ['Mckenna Lynn']
    roles = sorted(str(r['role']) for r in conn.execute('SELECT role FROM scene_people WHERE person_id = ?', (first,)))
    assert roles == ['actor', 'director']


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


def test_a_recased_honorific_folds_into_the_canonical_row_and_keeps_its_gender() -> None:
    conn = db.connect()
    with conn:
        conn.execute("INSERT INTO people(name, gender) VALUES('Mz Dani', 'female'), ('Mz. Dani', '')")
        stale, canonical = (int(r['id']) for r in conn.execute('SELECT id FROM people ORDER BY id'))
        conn.execute(
            'INSERT INTO scenes(hash, site, cur_id, rel_path, identifier, rating_key, guid, title, updated_at)'
            " VALUES('h','s','c','scenes/h/h','i','rk','g','T',0)"
        )
        scene = int(conn.execute('SELECT id FROM scenes').fetchone()['id'])
        conn.execute('INSERT INTO scene_people(scene_id, person_id, role, pos) VALUES(?,?,?,0)', (scene, stale, 'actor'))

    with conn:
        db._fold_recased_duplicate_names(conn)

    rows = conn.execute('SELECT id, name, gender FROM people').fetchall()
    assert [(str(r['name']), str(r['gender'])) for r in rows] == [('Mz. Dani', 'female')]
    assert int(rows[0]['id']) == canonical
    assert int(conn.execute('SELECT person_id FROM scene_people').fetchone()['person_id']) == canonical


def test_a_lone_noncanonical_name_is_recased_in_place() -> None:
    conn = db.connect()
    with conn:
        conn.execute("INSERT INTO people(name) VALUES('Whitney Oc'), ('Mackenzie Mace')")

    with conn:
        db._recase_noncanonical_names(conn)

    assert sorted(str(r['name']) for r in conn.execute('SELECT name FROM people')) == ['Mackenzie Mace', 'Whitney OC']


def test_recasing_folds_a_duplicate_before_touching_the_stale_row() -> None:
    conn = db.connect()
    with conn:
        conn.execute('DROP INDEX people_ci_global')
        conn.execute("INSERT INTO people(name, gender) VALUES('Whitney Oc', 'female'), ('Whitney OC', '')")

    with conn:
        db._recase_noncanonical_names(conn)

    rows = conn.execute('SELECT name, gender FROM people').fetchall()
    assert [(str(r['name']), str(r['gender'])) for r in rows] == [('Whitney OC', 'female')]


def test_genre_casing_follows_the_genre_map_not_title_case() -> None:
    conn = db.connect()
    with conn:
        conn.execute("INSERT INTO genres(name) VALUES('Caucasian (Female)'), ('Ebony (male)'), ('bbw tag')")

    with conn:
        db._recase_noncanonical_names(conn)

    names = sorted(str(r['name']) for r in conn.execute('SELECT name FROM genres'))
    assert names == ['BBW Tag', 'Caucasian (female)', 'Ebony (male)']


def test_genuine_spelling_variants_are_never_folded() -> None:
    conn = db.connect()
    with conn:
        conn.execute("INSERT INTO genres(name) VALUES('Glory Hole'), ('Gloryhole'), ('New Years'), ('BBC Pie'), ('Bbcpie')")

    with conn:
        db._fold_recased_duplicate_names(conn)

    names = sorted(str(r['name']) for r in conn.execute('SELECT name FROM genres'))
    assert names == ['BBC Pie', 'Bbcpie', 'Glory Hole', 'Gloryhole', 'New Years']


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
