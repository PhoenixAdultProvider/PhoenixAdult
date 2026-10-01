from __future__ import annotations

import pytest

from phoenixadult.utils.plex import client_hits


def test_client_hits_keep_only_the_most_recent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_hits, '_MAX_CLIENTS', 3)
    for i in range(5):
        client_hits.record(f'c{i}', {}, '/p')
    assert {h['clientId'] for h in client_hits.list_hits()} <= {'c2', 'c3', 'c4'}
    assert len(client_hits.list_hits()) == 3
