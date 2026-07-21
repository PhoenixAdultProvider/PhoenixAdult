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
