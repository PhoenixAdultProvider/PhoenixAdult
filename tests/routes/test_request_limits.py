from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from phoenixadult.registry import get_all_providers
from phoenixadult.utils.plex.media_type import provider_mount_path
from tests.conftest import plex_client

MOUNT = provider_mount_path(get_all_providers()[0])


@pytest.fixture
def plex(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv('API_REQUESTS_PER_DAY', '3')
    return plex_client()


def _as(client: TestClient, client_id: str) -> int:
    return client.get(MOUNT, headers={'X-Plex-Client-Identifier': client_id}).status_code


def test_a_client_is_cut_off_after_its_daily_allowance(plex: TestClient) -> None:
    assert [_as(plex, 'noisy') for _ in range(3)] == [200, 200, 200]
    assert _as(plex, 'noisy') == 429


def test_one_client_running_out_does_not_starve_another(plex: TestClient) -> None:
    for _ in range(4):
        _as(plex, 'noisy')
    assert _as(plex, 'noisy') == 429
    assert _as(plex, 'quiet') == 200, 'each client gets its own daily budget'


def test_the_limit_also_applies_per_api_key(plex: TestClient) -> None:
    from phoenixadult.utils.auth import user_store

    uid = user_store.create_user('keyholder', 'Hunter2hunter!', is_admin=True)
    key = user_store.regenerate_api_key(uid)
    for _ in range(3):
        assert plex.get(MOUNT, params={'apikey': key}).status_code == 200
    assert plex.get(MOUNT, params={'apikey': key}).status_code == 429, 'the key is capped even as the client id varies'


def test_regenerating_the_key_does_not_reset_the_daily_limit(plex: TestClient) -> None:
    from phoenixadult.utils.auth import user_store

    uid = user_store.create_user('rotator', 'Hunter2hunter!', is_admin=True)
    key = user_store.regenerate_api_key(uid)
    for _ in range(4):
        plex.get(MOUNT, params={'apikey': key})
    assert plex.get(MOUNT, params={'apikey': key}).status_code == 429
    fresh = user_store.regenerate_api_key(uid)
    assert plex.get(MOUNT, params={'apikey': fresh}).status_code == 429, 'the budget belongs to the user, not the key'


def test_a_throttled_response_says_when_to_come_back(plex: TestClient) -> None:
    for _ in range(4):
        _as(plex, 'noisy')
    r = plex.get(MOUNT, headers={'X-Plex-Client-Identifier': 'noisy'})
    assert r.status_code == 429
    assert 0 < int(r.headers['retry-after']) <= 86400


def test_no_limit_is_enforced_by_default() -> None:
    client = plex_client()
    for _ in range(6):
        assert _as(client, 'anyone') == 200


def test_counters_roll_over_to_the_next_day() -> None:
    from phoenixadult.utils.plex import daily_quota

    for _ in range(5):
        daily_quota.bump('client', 'noisy', day='2026-08-06')
    assert daily_quota.usage('client', 'noisy', day='2026-08-06') == 5
    assert daily_quota.usage('client', 'noisy', day='2026-08-07') == 0


def test_counts_survive_a_restart() -> None:
    from phoenixadult.utils import db
    from phoenixadult.utils.plex import client_hits, daily_quota

    client_hits.record('persisted-client', {'user-agent': 'PlexMediaServer/1.0', 'x-plex-product': 'PMS'}, '/phoenixadult/movies')
    daily_quota.bump('client', 'persisted-client')
    db.close()

    hits = client_hits.list_hits()
    assert [h['clientId'] for h in hits] == ['persisted-client']
    assert hits[0]['count'] == 1
    assert hits[0]['headers']['x-plex-product'] == 'PMS'
    assert daily_quota.usage('client', 'persisted-client') == 1
