from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from app.services import plex_reconcile as pr
from app.utils import cache as metadata_cache

# RFC 5737 documentation range — never a real host.
BASE = 'http://192.0.2.10:32400'
GUID = 'tv.plex.agents.custom.myprovider.phoenixadult://movie/scene-brazzers-abc123'
FOREIGN_GUID = 'plex://movie/5d776b9ad'


@pytest.fixture(autouse=True)
def _plex_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('PLEX_URL', BASE)
    monkeypatch.setenv('PLEX_TOKEN', 'test-token')


def _snapshot(**tags: list[str]) -> dict[str, Any]:
    md: dict[str, Any] = {'title': 'T'}
    for name, values in tags.items():
        md[name] = [{'tag': v} for v in values]
    return {'MediaContainer': {'Metadata': [md]}}


def _mock_plex(item: dict[str, Any], guid: str = GUID) -> respx.Route:
    respx.get(f'{BASE}/library/sections').mock(
        return_value=httpx.Response(200, json={'MediaContainer': {'Directory': [{'key': '1', 'type': 'movie'}, {'key': '2', 'type': 'show'}]}})
    )
    respx.get(url__startswith=f'{BASE}/library/sections/1/all').mock(
        return_value=httpx.Response(200, json={'MediaContainer': {'Metadata': [{'ratingKey': '77', 'guid': guid, 'title': 'A Scene'}]}})
    )
    respx.get(url__startswith=f'{BASE}/library/metadata/77').mock(return_value=httpx.Response(200, json={'MediaContainer': {'Metadata': [item]}}))
    return respx.put(url__startswith=f'{BASE}/library/sections/1/all').mock(return_value=httpx.Response(200))


def test_enabled_requires_both_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    assert pr.enabled() is True
    monkeypatch.delenv('PLEX_TOKEN')
    assert pr.enabled() is False
    monkeypatch.setenv('PLEX_TOKEN', 't')
    monkeypatch.delenv('PLEX_URL')
    assert pr.enabled() is False


def test_our_rating_key_only_matches_our_guids() -> None:
    assert pr._our_rating_key(GUID) == 'scene-brazzers-abc123'
    assert pr._our_rating_key(FOREIGN_GUID) is None
    assert pr._our_rating_key('') is None


@respx.mock
async def test_dry_run_reports_but_does_not_write(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(metadata_cache, 'read', lambda s, c: _snapshot(Collection=['Teens Like It Big'], Genre=['Anal']))
    put = _mock_plex({'Collection': [{'tag': 'Brazzers'}, {'tag': 'Teens Like It Big'}], 'Genre': [{'tag': 'Anal'}]})

    report = await pr.reconcile(apply=False)
    assert report.applied is False
    assert report.matched == 1 and report.changed == 1
    assert report.items[0].removals == {'Collection': ['Brazzers']}
    assert not put.called  # nothing written


@respx.mock
async def test_apply_removes_stale_tags_and_keeps_field_unlocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(metadata_cache, 'read', lambda s, c: _snapshot(Collection=['Teens Like It Big']))
    put = _mock_plex({'Collection': [{'tag': 'Brazzers'}, {'tag': 'Teens Like It Big'}]})

    report = await pr.reconcile(apply=True)
    assert report.applied is True and report.changed == 1
    assert put.called
    params = put.calls[0].request.url.params
    assert params['id'] == '77'
    assert params['collection[].tag.tag-'] == 'Brazzers'
    assert params['collection.locked'] == '0'  # editing would otherwise lock the field forever


@respx.mock
async def test_role_maps_to_the_actor_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(metadata_cache, 'read', lambda s, c: _snapshot(Role=['Gina Gerson']))
    put = _mock_plex({'Role': [{'tag': 'Gina Gerson'}, {'tag': 'Ghost Actor'}]})

    await pr.reconcile(apply=True)
    params = put.calls[0].request.url.params
    assert params['actor[].tag.tag-'] == 'Ghost Actor'


@respx.mock
async def test_locked_field_is_skipped_and_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(metadata_cache, 'read', lambda s, c: _snapshot(Collection=['Teens Like It Big']))
    put = _mock_plex(
        {
            'Collection': [{'tag': 'Brazzers'}, {'tag': 'Teens Like It Big'}],
            'Field': [{'name': 'collection', 'locked': True}],
        }
    )

    report = await pr.reconcile(apply=True)
    assert report.changed == 0
    assert report.skipped_locked == 1
    assert report.items[0].locked == ['Collection']
    assert not put.called  # a hand-curated field is never overwritten


@respx.mock
async def test_scene_without_a_snapshot_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(metadata_cache, 'read', lambda s, c: None)
    put = _mock_plex({'Collection': [{'tag': 'Brazzers'}]})

    report = await pr.reconcile(apply=True)
    assert report.skipped_no_snapshot == 1 and report.changed == 0
    assert report.items[0].skipped == 'no snapshot'
    assert not put.called


@respx.mock
async def test_items_from_other_agents_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(metadata_cache, 'read', lambda s, c: _snapshot(Collection=[]))
    put = _mock_plex({'Collection': [{'tag': 'Whatever'}]}, guid=FOREIGN_GUID)

    report = await pr.reconcile(apply=True)
    assert report.scanned == 1 and report.matched == 0 and report.changed == 0
    assert not put.called


@respx.mock
async def test_token_is_sent_as_a_header_not_a_query_param(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(metadata_cache, 'read', lambda s, c: _snapshot(Collection=['Teens Like It Big']))
    _mock_plex({'Collection': [{'tag': 'Teens Like It Big'}]})

    await pr.reconcile(apply=False)
    req = respx.calls[0].request
    assert req.headers['X-Plex-Token'] == 'test-token'
    assert 'X-Plex-Token' not in str(req.url)
