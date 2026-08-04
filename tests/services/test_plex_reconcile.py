from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from phoenixadult.services import plex_reconcile as pr
from phoenixadult.utils.cache import scene_store

BASE = 'http://192.0.2.10:32400'
GUID = 'tv.plex.agents.custom.phoenixadult://movie/scene-brazzers-abc123'
FOREIGN_GUID = 'plex://movie/5d776b9ad'


@pytest.fixture(autouse=True)
def _plex_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('PLEX_URL', BASE)
    monkeypatch.setenv('PLEX_TOKEN', 'test-token')
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.delenv('ADMIN_TOKEN', raising=False)


def _snapshot(**tags: list[str]) -> dict[str, list[str]]:
    return {name: tags.get(name, []) for name in pr._FIELDS}


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
    monkeypatch.setattr(scene_store, 'tags_for', lambda s, c: _snapshot(Collection=['Teens Like It Big'], Genre=['Anal']))
    put = _mock_plex({'Collection': [{'tag': 'Brazzers'}, {'tag': 'Teens Like It Big'}], 'Genre': [{'tag': 'Anal'}]})

    report = await pr.reconcile(apply=False)
    assert report.applied is False
    assert report.matched == 1 and report.changed == 1
    assert report.items[0].removals == {'Collection': ['Brazzers']}
    assert not put.called


@respx.mock
async def test_items_are_inspected_concurrently(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    monkeypatch.setattr(scene_store, 'tags_for', lambda s, c: _snapshot(Genre=['Anal']))
    stubs = [{'ratingKey': str(100 + i), 'guid': f'{GUID[:-1]}{i}', 'title': f'Scene {i}'} for i in range(8)]
    respx.get(f'{BASE}/library/sections').mock(return_value=httpx.Response(200, json={'MediaContainer': {'Directory': [{'key': '1', 'type': 'movie'}]}}))
    respx.get(url__startswith=f'{BASE}/library/sections/1/all').mock(return_value=httpx.Response(200, json={'MediaContainer': {'Metadata': stubs}}))
    respx.get(url__regex=rf'{BASE}/library/metadata/\d+').mock(return_value=httpx.Response(200, json={'MediaContainer': {'Metadata': [{}]}}))

    in_flight = 0
    peak = 0
    original = pr.PlexClient.item

    async def tracked(self: pr.PlexClient, rating_key: str) -> dict[str, Any]:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        try:
            return await original(self, rating_key)
        finally:
            in_flight -= 1

    monkeypatch.setattr(pr.PlexClient, 'item', tracked)
    report = await pr.reconcile(apply=False)
    assert report.matched == 8 and report.scanned == 8
    assert [i.rating_key for i in report.items] == []
    assert peak > 1
    assert pr.progress() == {'active': False, 'total': 8, 'inspected': 8}


@respx.mock
async def test_apply_removes_stale_tags_and_keeps_field_unlocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scene_store, 'tags_for', lambda s, c: _snapshot(Collection=['Teens Like It Big']))
    put = _mock_plex({'Collection': [{'tag': 'Brazzers'}, {'tag': 'Teens Like It Big'}]})

    report = await pr.reconcile(apply=True)
    assert report.applied is True and report.changed == 1
    assert put.called
    params = put.calls[0].request.url.params
    assert params['id'] == '77'
    assert params['collection[0].tag.tag'] == 'Teens Like It Big'
    assert 'collection[1].tag.tag' not in params
    assert params['collection.locked'] == '0'


@respx.mock
async def test_role_maps_to_the_actor_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scene_store, 'tags_for', lambda s, c: _snapshot(Role=['Gina Gerson']))
    put = _mock_plex({'Role': [{'tag': 'Gina Gerson'}, {'tag': 'Ghost Actor'}]})

    await pr.reconcile(apply=True)
    params = put.calls[0].request.url.params
    assert params['actor[].tag.tag-'] == 'Ghost Actor'


@respx.mock
async def test_locked_field_is_skipped_and_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scene_store, 'tags_for', lambda s, c: _snapshot(Collection=['Teens Like It Big']))
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
    assert not put.called


@respx.mock
async def test_scene_without_a_snapshot_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scene_store, 'tags_for', lambda s, c: None)
    put = _mock_plex({'Collection': [{'tag': 'Brazzers'}]})

    report = await pr.reconcile(apply=True)
    assert report.skipped_no_snapshot == 1 and report.changed == 0
    assert report.items[0].skipped == 'no snapshot'
    assert not put.called


@respx.mock
async def test_items_from_other_agents_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scene_store, 'tags_for', lambda s, c: _snapshot(Collection=[]))
    put = _mock_plex({'Collection': [{'tag': 'Whatever'}]}, guid=FOREIGN_GUID)

    report = await pr.reconcile(apply=True)
    assert report.scanned == 1 and report.matched == 0 and report.changed == 0
    assert not put.called


@respx.mock
async def test_token_is_sent_as_a_header_not_a_query_param(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scene_store, 'tags_for', lambda s, c: _snapshot(Collection=['Teens Like It Big']))
    _mock_plex({'Collection': [{'tag': 'Teens Like It Big'}]})

    await pr.reconcile(apply=False)
    req = respx.calls[0].request
    assert req.headers['X-Plex-Token'] == 'test-token'
    assert 'X-Plex-Token' not in str(req.url)


@respx.mock
async def test_field_filter_restricts_removal_types(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scene_store, 'tags_for', lambda s, c: _snapshot(Collection=['Keep'], Genre=['Keep']))
    _mock_plex({'ratingKey': '77', 'guid': GUID, 'title': 'A Scene', 'Collection': [{'tag': 'Stale C'}], 'Genre': [{'tag': 'Stale G'}]})
    report = await pr.reconcile(fields={'Genre'})
    assert report.items[0].removals == {'Genre': ['Stale G']}
    assert report.items[0].site == 'brazzers'


@respx.mock
async def test_site_filter_skips_other_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scene_store, 'tags_for', lambda s, c: _snapshot(Genre=['Keep']))
    _mock_plex({'ratingKey': '77', 'guid': GUID, 'title': 'A Scene', 'Genre': [{'tag': 'Stale G'}]})
    report = await pr.reconcile(sites={'nubilefilms'})
    assert report.changed == 0
    report = await pr.reconcile(sites={'Brazzers'})
    assert report.changed == 1


def _mock_collections(candidates: list[str]) -> tuple[respx.Route, respx.Route]:
    respx.get(f'{BASE}/library/sections').mock(return_value=httpx.Response(200, json={'MediaContainer': {'Directory': [{'key': '1', 'type': 'movie'}]}}))
    respx.get(f'{BASE}/library/sections/1/collections').mock(
        return_value=httpx.Response(200, json={'MediaContainer': {'Metadata': [{'ratingKey': '900', 'title': 'Baby Got Boobs'}]}})
    )
    respx.get(url__startswith=f'{BASE}/library/metadata/900/clearLogos').mock(
        return_value=httpx.Response(200, json={'MediaContainer': {'Metadata': [{'key': k} for k in candidates]}})
    )
    post = respx.post(url__startswith=f'{BASE}/library/metadata/900/clearLogos').mock(return_value=httpx.Response(200))
    put = respx.put(url__startswith=f'{BASE}/library/metadata/900/clearLogo').mock(return_value=httpx.Response(200))
    return post, put


@respx.mock
async def test_collection_logos_pushes_matching_logo(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    (tmp_path / 'logos' / 'brazzers').mkdir(parents=True)
    (tmp_path / 'logos' / 'brazzers' / 'logo.baby-got-boobs.png').write_bytes(b'png')
    monkeypatch.setenv('IMAGE_DIR', str(tmp_path))
    from phoenixadult.utils.images import logo_cache

    logo_cache.invalidate()
    monkeypatch.setattr('phoenixadult.config.image_base_url', lambda: 'http://192.0.2.20:3000')
    post, put = _mock_collections(candidates=[])

    report = await pr.push_collection_logos(apply=True)
    assert report.collections == 1 and report.matched == 1 and report.pushed == 1 and report.already == 0
    assert post.called and put.called
    assert put.calls[0].request.url.params['url'] == 'http://192.0.2.20:3000/images/local/logos/brazzers/logo.baby-got-boobs.png'


@respx.mock
async def test_collection_logos_skips_already_pushed(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    (tmp_path / 'logos' / 'brazzers').mkdir(parents=True)
    (tmp_path / 'logos' / 'brazzers' / 'logo.baby-got-boobs.png').write_bytes(b'png')
    monkeypatch.setenv('IMAGE_DIR', str(tmp_path))
    from phoenixadult.utils.images import logo_cache

    logo_cache.invalidate()
    post, put = _mock_collections(candidates=['http://any:3000/images/local/logos/brazzers/logo.baby-got-boobs.png'])

    report = await pr.push_collection_logos(apply=True)
    assert report.matched == 1 and report.already == 1 and report.pushed == 0
    assert not post.called and not put.called
