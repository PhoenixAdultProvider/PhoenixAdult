from __future__ import annotations

from pathlib import Path

import pytest

from phoenixadult.config.env import env
from phoenixadult.utils.fs.reloadable import MtimeCachedJson
from phoenixadult.utils.images import face_crop_log
from phoenixadult.utils.plex import client_hits


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
