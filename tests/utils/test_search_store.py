from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from app.clients.base import SearchResult
from app.utils.cache import search_store

KEY = ('Nubile Films', 'cool scene', '2024-01-01', '', '')


@pytest.fixture(autouse=True)
def _store_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv('SEARCH_QUEUE_DIR', str(tmp_path))
    return tmp_path


def test_normalize_text_lowers_and_collapses_whitespace() -> None:
    assert search_store.normalize_text('  Cool   SCENE ') == 'cool scene'


def test_round_trip_preserves_results() -> None:
    results = [SearchResult(title='Found', scene_url='https://x/1', cur_id='abc', score=100.0)]
    search_store.save(KEY, results)
    loaded = search_store.load(KEY)
    assert loaded is not None
    assert loaded[0] == results[0]


def test_empty_results_are_not_persisted(_store_dir: Path) -> None:
    search_store.save(KEY, [SearchResult(title='Old', scene_url='https://x/1', cur_id='abc')])
    search_store.save(KEY, [])
    assert search_store.load(KEY) is None
    assert not list(_store_dir.glob('*.json'))


def test_stored_empty_results_are_treated_as_a_miss(_store_dir: Path) -> None:
    search_store.save(KEY, [SearchResult(title='Old', scene_url='https://x/1', cur_id='abc')])
    path = next(_store_dir.glob('*.json'))
    payload = json.loads(path.read_text(encoding='utf-8'))
    payload['results'] = []
    path.write_text(json.dumps(payload), encoding='utf-8')
    assert search_store.load(KEY) is None
    assert not path.exists()


def test_miss_and_corrupt_file_return_none(_store_dir: Path) -> None:
    assert search_store.load(KEY) is None
    search_store.save(KEY, [SearchResult(title='X', scene_url='https://x/1', cur_id='abc')])
    next(_store_dir.glob('*.json')).write_text('not json', encoding='utf-8')
    assert search_store.load(KEY) is None


def test_expired_entry_is_dropped(_store_dir: Path) -> None:
    search_store.save(KEY, [SearchResult(title='Old', scene_url='https://x/1', cur_id='abc')])
    path = next(_store_dir.glob('*.json'))
    payload = json.loads(path.read_text(encoding='utf-8'))
    payload['saved_at'] = time.time() - search_store._STORE_TTL - 1
    path.write_text(json.dumps(payload), encoding='utf-8')
    assert search_store.load(KEY) is None
    assert not path.exists()


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
