from __future__ import annotations

import json
from pathlib import Path

import pytest

from phoenixadult.config.env import env
from phoenixadult.models.scrape import SearchResult
from phoenixadult.utils import db
from phoenixadult.utils.cache import scene_store, search_store
from phoenixadult.utils.fs.reloadable import MtimeCachedJson
from phoenixadult.utils.images import face_crop_log
from phoenixadult.utils.plex import client_hits


def test_a_percent_in_the_search_filter_is_literal() -> None:
    search_store.save(('Site', 'plain', '2024-01-01', '', ''), [SearchResult(title='Plain', scene_url='https://x/1', cur_id='a')])
    search_store.save(('Site', '100% real', '2024-01-02', '', ''), [SearchResult(title='Real', scene_url='https://x/2', cur_id='b')])
    page = search_store.dump_page(needle='100%')
    assert [row['title'] for members in page['groups'] for row in members] == ['100% real']


def test_a_stored_result_from_an_older_shape_reads_as_a_miss() -> None:
    key = ('Site', 'old', '2024-01-01', '', '')
    search_store.save(key, [SearchResult(title='Old', scene_url='https://x/1', cur_id='a')])
    conn = db.connect()
    conn.execute('UPDATE search_results SET payload = ?', (json.dumps({'title': 'Old', 'retired_field': 1}),))
    conn.commit()
    assert search_store.load(key) is None


def test_the_change_token_moves_when_locks_change() -> None:
    scene_store.upsert('Site', 'cur', 'hash1', 'scenes/ha/hash1', {'MediaContainer': {'identifier': 'p', 'Metadata': [{'title': 'T'}]}})
    before = scene_store.change_token()
    scene_store.set_locks('hash1', ['title'], False)
    assert scene_store.change_token() != before


def test_flagging_a_person_ignores_case() -> None:
    md = {'title': 'T', 'Role': [{'tag': 'Jane Doe'}]}
    scene_store.upsert('Site', 'cur', 'hash1', 'scenes/ha/hash1', {'MediaContainer': {'identifier': 'p', 'Metadata': [md]}})
    assert scene_store.flag_people_changed('jane doe') == ['T']


def test_relabelling_to_unrecorded_clears_the_source() -> None:
    directory = str(Path(env.people_cache_dir) / 'actors' / 'female')
    face_crop_log.record(
        directory, name='A', filename='actor.a_female.jpg', base='actor.a_female', orig_ext='.jpg', upstream_url='', cropped=False, source='IAFD'
    )
    assert face_crop_log.update(directory, 'actor.a_female.jpg', source='')
    entry = face_crop_log.entry_for(directory, 'actor.a_female.jpg')
    assert entry is not None and entry['source'] == ''


def test_client_hits_keep_only_the_most_recent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_hits, '_MAX_CLIENTS', 3)
    for i in range(5):
        client_hits.record(f'c{i}', {}, '/p')
    assert {h['clientId'] for h in client_hits.list_hits()} <= {'c2', 'c3', 'c4'}
    assert len(client_hits.list_hits()) == 3


def test_a_broken_reload_keeps_the_last_good_copy(tmp_path: Path) -> None:
    data = tmp_path / 'rules.json'
    data.write_text('{"a": 1}', encoding='utf-8')
    cached = MtimeCachedJson(data, lambda raw: raw['a'], stat_interval=0)
    assert cached.get() == 1
    data.write_text('{not json', encoding='utf-8')
    assert cached.get() == 1
