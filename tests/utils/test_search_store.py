from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from phoenixadult.clients.base import SearchResult
from phoenixadult.utils import db
from phoenixadult.utils.cache import search_store

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


def test_perpetual_by_default_never_expires() -> None:
    search_store.save(KEY, [SearchResult(title='Old', scene_url='https://x/1', cur_id='abc')])
    db.connect().execute('UPDATE searches SET saved_at = ?', (time.time() - 3650 * 86400,))
    assert search_store.load(KEY) is not None
    assert search_store.sweep_expired() == 0


def test_expired_entry_is_dropped_when_ttl_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('SEARCH_STORE_TTL_DAYS', '7')
    search_store.save(KEY, [SearchResult(title='Old', scene_url='https://x/1', cur_id='abc')])
    db.connect().execute('UPDATE searches SET saved_at = ?', (time.time() - 8 * 86400,))
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
    assert search_store.load_similar(('Bratty Sis', 'hailey rose', '2024-06-21', '555', '')) is None, 'a scene id mismatch is a different search'


def test_load_similar_matches_any_rename_on_the_same_date() -> None:
    search_store.save(('Bratty Sis', 'hailey rose', '2024-06-21', '', ''), [SearchResult(title='X', scene_url='https://x/2', cur_id='bs1')])
    hit = search_store.load_similar(('Bratty Sis', 'unrelated title', '2024-06-21', '', ''))
    assert hit is not None and hit[0].cur_id == 'bs1', 'results are keyed by site+date+id; the title only ever scored them'


def test_load_similar_survives_word_substitution_and_insertion() -> None:
    old_fs = ('Family Swap', 'jessica ryan and michelle anthony 4th of july family shootout', '2021-06-27', '', '')
    search_store.save(old_fs, [SearchResult(title='4th of July Family Shootout', scene_url='https://x/fs', cur_id='fs1')])
    renamed_fs = ('Family Swap', 'jessica ryan and michelle anthony fourth of july family shootout', '2021-06-27', '', '')
    hit = search_store.load_similar(renamed_fs)
    assert hit is not None and hit[0].cur_id == 'fs1', '4th -> fourth is a word substitution, not a substring'

    old_css = ('Cum Swapping Sis', 'molly little and scarlet skies black friday deal', '2022-11-28', '', '')
    search_store.save(old_css, [SearchResult(title='Black Friday Deal', scene_url='https://x/css', cur_id='css1')])
    renamed_css = ('Cum Swapping Sis', 'molly little and scarlet skies stepsisters black friday deal', '2022-11-28', '', '')
    hit = search_store.load_similar(renamed_css)
    assert hit is not None and hit[0].cur_id == 'css1', 'a mid-title insertion breaks substring containment'


def test_load_similar_prefers_the_newest_stored_search(monkeypatch) -> None:
    import time as _time

    search_store._write(
        ('Bratty Sis', 'old scrape', '2024-06-21', '', ''), [SearchResult(title='Old', scene_url='https://x/o', cur_id='old')], _time.time() - 500
    )
    search_store._write(('Bratty Sis', 'new scrape', '2024-06-21', '', ''), [SearchResult(title='New', scene_url='https://x/n', cur_id='new')], _time.time())
    hit = search_store.load_similar(('Bratty Sis', 'renamed again', '2024-06-21', '', ''))
    assert hit is not None and hit[0].cur_id == 'new'


def test_find_title_resolves_cur_id_to_stored_result() -> None:
    search_store.save(KEY, [SearchResult(title='Only You', scene_url='https://x/3', cur_id='xyz9', subsite='Girls Only Porn')])
    assert search_store.find_title('xyz9') == ('Only You', 'Girls Only Porn')
    assert search_store.find_title('missing') is None
    assert search_store.find_title('') is None


def test_sweep_expired_deletes_only_stale_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('SEARCH_STORE_TTL_DAYS', '7')
    search_store.save(KEY, [SearchResult(title='Fresh', scene_url='https://x/1', cur_id='abc')])
    stale = ('Bratty Sis', 'old scene', '2020-01-01', '', '')
    search_store.save(stale, [SearchResult(title='Old', scene_url='https://x/2', cur_id='old1')])
    db.connect().execute("UPDATE searches SET saved_at = ? WHERE site = 'Bratty Sis'", (time.time() - 8 * 86400,))
    assert search_store.sweep_expired() == 1
    assert search_store.load(KEY) is not None
