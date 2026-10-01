from __future__ import annotations

from pathlib import Path

import pytest

from phoenixadult.utils.fs.reloadable import MtimeCachedJson
from phoenixadult.utils.plex import client_hits


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
