from __future__ import annotations

from pathlib import Path

import pytest

from phoenixadult.utils import db

_WANTED = {
    'scene_people_person',
    'scene_people_role_person',
    'scene_genres_genre',
    'scene_collections_collection',
    'scene_countries_country',
}


@pytest.fixture()
def fresh(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv('STATE_DB_PATH', str(tmp_path / 'phoenixadult.db'))
    db.close()


def test_junction_tables_are_indexed_on_the_column_we_query_by(fresh: None) -> None:
    conn = db.connect()
    have = {str(r['name']) for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert _WANTED <= have, f'missing {sorted(_WANTED - have)}'


def test_person_lookups_search_rather_than_scan(fresh: None) -> None:
    conn = db.connect()
    sql = 'SELECT s.hash FROM scenes s JOIN scene_people sp ON sp.scene_id = s.id JOIN people p ON p.id = sp.person_id WHERE p.name = ?'
    plan = [str(row[3]) for row in conn.execute('EXPLAIN QUERY PLAN ' + sql, ('Jane Doe',))]
    assert not [step for step in plan if step.startswith('SCAN')], f'a person lookup still scans a whole table: {plan}'


def test_applying_the_indexes_twice_is_harmless(fresh: None) -> None:
    db.connect()
    db.close()
    conn = db.connect()
    have = {str(r['name']) for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert _WANTED <= have
