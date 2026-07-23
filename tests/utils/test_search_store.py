from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.clients.base import SearchResult
from app.utils import db
from app.utils.cache import search_store

KEY = ('Nubile Films', 'cool scene', '2024-01-01', '', '')


@pytest.fixture(autouse=True)
def _store_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    monkeypatch.setenv('STATE_DB_PATH', str(tmp_path / 'state.db'))
    yield tmp_path
    db.close()


def test_normalize_text_lowers_and_collapses_whitespace() -> None:
    assert search_store.normalize_text('  Cool   SCENE ') == 'cool scene'


def test_round_trip_preserves_results() -> None:
    results = [SearchResult(title='Found', scene_url='https://x/1', cur_id='abc', score=100.0)]
    search_store.save(KEY, results)
    loaded = search_store.load(KEY)
    assert loaded is not None
    assert loaded[0] == results[0]


def test_empty_results_are_not_persisted() -> None:
    search_store.save(KEY, [SearchResult(title='Old', scene_url='https://x/1', cur_id='abc')])
    search_store.save(KEY, [])
    assert search_store.load(KEY) is None


def test_expired_entry_is_dropped() -> None:
    search_store.save(KEY, [SearchResult(title='Old', scene_url='https://x/1', cur_id='abc')])
    db.connect().execute('UPDATE searches SET saved_at = ?', (time.time() - search_store._STORE_TTL - 1,))
    assert search_store.load(KEY) is None
    assert db.connect().execute('SELECT COUNT(*) c FROM searches').fetchone()['c'] == 0


def test_load_similar_matches_longer_renamed_query() -> None:
    old_key = ('Bratty Sis', 'hailey rose', '2024-06-21', '', '')
    search_store.save(old_key, [SearchResult(title='Stepsisters Mean Pussy', scene_url='https://x/2', cur_id='bs1')])
    new_key = ('Bratty Sis', 'hailey rose stepsisters mean pussy', '2024-06-21', '', '')
    similar = search_store.load_similar(new_key)
    assert similar is not None and similar[0].cur_id == 'bs1'


def test_load_similar_requires_same_site_and_date() -> None:
    search_store.save(('Bratty Sis', 'hailey rose', '2024-06-21', '', ''), [SearchResult(title='X', scene_url='https://x/2', cur_id='bs1')])
    assert search_store.load_similar(('Bratty Sis', 'hailey rose extra', '2024-06-22', '', '')) is None
    assert search_store.load_similar(('My Family Pies', 'hailey rose extra', '2024-06-21', '', '')) is None
    assert search_store.load_similar(('Bratty Sis', 'unrelated title', '2024-06-21', '', '')) is None


def test_find_title_resolves_cur_id_to_stored_result() -> None:
    search_store.save(KEY, [SearchResult(title='Only You', scene_url='https://x/3', cur_id='xyz9', subsite='Girls Only Porn')])
    assert search_store.find_title('xyz9') == ('Only You', 'Girls Only Porn')
    assert search_store.find_title('missing') is None
    assert search_store.find_title('') is None


def test_sweep_expired_deletes_only_stale_rows() -> None:
    search_store.save(KEY, [SearchResult(title='Fresh', scene_url='https://x/1', cur_id='abc')])
    stale = ('Bratty Sis', 'old scene', '2020-01-01', '', '')
    search_store.save(stale, [SearchResult(title='Old', scene_url='https://x/2', cur_id='old1')])
    db.connect().execute("UPDATE searches SET saved_at = ? WHERE site = 'Bratty Sis'", (time.time() - search_store._STORE_TTL - 1,))
    assert search_store.sweep_expired() == 1
    assert search_store.load(KEY) is not None
