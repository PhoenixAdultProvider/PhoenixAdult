from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from phoenixadult.utils.cache import layout as cache_layout
from phoenixadult.utils.cache import listing as cache_listing
from tests.support import authed_client


def test_requires_auth() -> None:
    assert TestClient(create_app()).get('/metadata', headers={'accept': 'application/json'}).status_code == 401
    page = authed_client().get('/metadata')
    assert page.status_code == 200
    assert 'Snapshot Metadata Cache' in page.text


def test_purge_validates(monkeypatch: pytest.MonkeyPatch) -> None:
    client = authed_client()
    assert client.post('/metadata/purge', json={}).status_code == 400
    r = client.post('/metadata/purge', json={'key': 'nope/abc'})
    assert r.status_code == 200 and r.json()['ok'] is False


def test_purge_bulk_validates_and_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    import phoenixadult.routes.metadata_cache_routes as mcr

    purged: list[str] = []

    def fake_purge(key: str) -> bool:
        purged.append(key)
        return key != 'studio/missing'

    monkeypatch.setattr(mcr.cache_listing, 'purge', fake_purge)
    client = authed_client()
    assert client.post('/metadata/purge-bulk', json={}).status_code == 400
    assert client.post('/metadata/purge-bulk', json={'keys': []}).status_code == 400
    assert client.post('/metadata/purge-bulk', json={'keys': 'studio/abc'}).status_code == 400
    assert client.post('/metadata/purge-bulk', json={'keys': ['noslash']}).status_code == 400
    assert client.post('/metadata/purge-bulk', json={'keys': ['studio/abc', 5]}).status_code == 400
    assert purged == []

    r = client.post('/metadata/purge-bulk', json={'keys': ['studio/abc', 'studio/missing', 'studio/sub/def']})
    assert r.status_code == 200 and r.json() == {'ok': True, 'purged': 2}
    assert purged == ['studio/abc', 'studio/missing', 'studio/sub/def']


def test_page_has_filtered_bulk_purge(monkeypatch: pytest.MonkeyPatch) -> None:
    import phoenixadult.routes.metadata_cache_routes as mcr

    monkeypatch.setattr(mcr.cache_duplicates, 'duplicate_entries', lambda: [])
    monkeypatch.setattr(mcr.cache_listing, 'entries', lambda: [])
    page = authed_client().get('/metadata')
    assert 'purgeShown()' in page.text
    assert 'This cannot be undone.' in page.text
    assert 'exportShown()' in page.text
    assert 'f-data18' in page.text
    assert 'data18_manual_mappings${suffix}.json' in page.text


def test_state_and_entries_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    import phoenixadult.routes.metadata_cache_routes as mcr

    monkeypatch.setattr(mcr.cache_listing, 'change_token', lambda: '3:123.0')
    monkeypatch.setattr(mcr.cache_listing, 'entries_page', lambda **_kw: ([{'key': 'studio/abc'}], 1))
    monkeypatch.setattr(mcr.cache_duplicates, 'duplicate_entries', lambda: ['studio/abc'])
    monkeypatch.setattr(mcr.cache_listing, 'studios', lambda **_kw: ['Studio'])
    monkeypatch.setattr(mcr.cache_listing, 'facets', lambda **_kw: {'taglines': ['T']})
    assert TestClient(create_app()).get('/metadata/state', headers={'accept': 'application/json'}).status_code == 401
    client = authed_client()
    assert client.get('/metadata/state').json() == {'token': '3:123.0'}
    assert client.get('/metadata/entries').json() == {
        'entries': [{'key': 'studio/abc'}],
        'dup_keys': ['studio/abc'],
        'total': 1,
        'studios': ['Studio'],
        'facets': {'taglines': ['T']},
    }


def test_page_persists_filters_and_polls(monkeypatch: pytest.MonkeyPatch) -> None:
    import phoenixadult.routes.metadata_cache_routes as mcr

    monkeypatch.setattr(mcr.cache_duplicates, 'duplicate_entries', lambda: [])
    monkeypatch.setattr(mcr.cache_listing, 'entries', lambda: [])
    page = authed_client().get('/metadata')
    assert 'metadata-cache-filters' in page.text
    assert 'restoreFilters()' in page.text
    assert "fetch('/metadata/state'" in page.text
    assert 'setInterval(pollState' in page.text


def test_page_injects_duplicate_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    import phoenixadult.routes.metadata_cache_routes as mcr

    monkeypatch.setattr(mcr.cache_duplicates, 'duplicate_entries', lambda: ['a/b/c', 'd/e/f'])
    monkeypatch.setattr(mcr.cache_listing, 'entries', lambda: [])
    page = authed_client().get('/metadata')
    assert 'var DUP_KEYS = ["a/b/c", "d/e/f"];' in page.text
    assert 'Show Duplicates' in page.text


def test_page_has_server_side_pagination(monkeypatch: pytest.MonkeyPatch) -> None:
    page = authed_client().get('/metadata')
    assert 'var TOTAL = 0;' in page.text
    assert 'var STUDIOS = [];' in page.text
    assert 'var PAGE_SIZE = 200;' in page.text
    assert 'serverQuery(PAGE_SIZE, true)' in page.text
    assert '>Previous<' in page.text and '>Next<' in page.text


def _seed_scene(site: str, cur: str, title: str, studio: str, date: str, updated: float) -> None:
    from phoenixadult.utils.cache import scene_store

    data = {
        'MediaContainer': {
            'identifier': 'i',
            'size': 1,
            'Metadata': [{'type': 'movie', 'ratingKey': 'rk', 'guid': 'g', 'title': title, 'studio': studio, 'originallyAvailableAt': date}],
        }
    }
    scene_store.upsert(site, cur, cache_layout.scene_hash_for(site, cur), f'{studio.lower()}/{cur}', data, updated_at=updated)


def _seed_library() -> None:
    _seed_scene('Brazzers', 'c1', 'Alpha Scene', 'Brazzers', '2024-01-01', 100.0)
    _seed_scene('Brazzers', 'c2', 'Bravo Scene', 'Brazzers', '2024-02-01', 200.0)
    _seed_scene('Vixen', 'c3', 'Charlie Night', 'Vixen', '2024-03-01', 300.0)
    _seed_scene('Vixen', 'c4', 'Delta Night', 'Vixen', '2024-04-01', 400.0)
    _seed_scene('Vixen', 'c5', 'Echo Scene', 'Vixen', '2024-05-01', 500.0)


def test_entries_endpoint_filters_sorts_and_paginates(monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_library()
    client = authed_client()

    j = client.get('/metadata/entries').json()
    assert j['total'] == 5 and len(j['entries']) == 5
    assert [e['title'] for e in j['entries']] == ['Echo Scene', 'Delta Night', 'Charlie Night', 'Bravo Scene', 'Alpha Scene']
    assert j['studios'] == ['Brazzers', 'Vixen']
    assert j['dup_keys'] == []

    j = client.get('/metadata/entries', params={'studio': 'Brazzers'}).json()
    assert j['total'] == 2
    assert {e['studio'] for e in j['entries']} == {'Brazzers'}

    j = client.get('/metadata/entries', params={'q': 'night'}).json()
    assert j['total'] == 2
    assert sorted(e['title'] for e in j['entries']) == ['Charlie Night', 'Delta Night']

    j = client.get('/metadata/entries', params={'sort': 'title', 'dir': 'asc'}).json()
    assert [e['title'] for e in j['entries']] == ['Alpha Scene', 'Bravo Scene', 'Charlie Night', 'Delta Night', 'Echo Scene']

    j = client.get('/metadata/entries', params={'sort': 'release_date', 'dir': 'desc'}).json()
    assert [e['date'] for e in j['entries']] == ['2024-05-01', '2024-04-01', '2024-03-01', '2024-02-01', '2024-01-01']

    j = client.get('/metadata/entries', params={'sort': 'title', 'dir': 'asc', 'limit': 2, 'offset': 2}).json()
    assert j['total'] == 5
    assert [e['title'] for e in j['entries']] == ['Charlie Night', 'Delta Night']

    j = client.get('/metadata/entries', params={'sort': 'bogus', 'dir': 'sideways'}).json()
    assert [e['title'] for e in j['entries']][0] == 'Echo Scene'

    j = client.get('/metadata/entries', params={'studio': 'Brazzers', 'q': 'alpha'}).json()
    assert j['total'] == 1 and j['entries'][0]['title'] == 'Alpha Scene'


def test_entries_facet_filters_paginate_consistently(monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_library()
    client = authed_client()

    j = client.get('/metadata/entries', params={'year': '2024', 'month': '03'}).json()
    assert j['total'] == 1 and j['entries'][0]['title'] == 'Charlie Night'

    j = client.get('/metadata/entries', params={'year': '2024', 'limit': 2, 'offset': 2}).json()
    assert j['total'] == 5 and len(j['entries']) == 2

    j = client.get('/metadata/entries', params={'tagline': '__blank__'}).json()
    assert j['total'] == 5

    j = client.get('/metadata/entries', params={'data18': '__set__'}).json()
    assert j['total'] == 0

    j = client.get('/metadata/entries', params={'limit': 0}).json()
    assert j['total'] == 5 and len(j['entries']) == 5

    facets = j['facets']
    assert facets['years'] == ['2024']
    assert facets['months'] == ['01', '02', '03', '04', '05']
    assert facets['tagline_blank'] is True


def test_entries_filter_by_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_library()
    client = authed_client()

    j = client.get('/metadata/entries').json()
    assert j['facets']['providers'] == ['Project1Service', 'Strike3']
    assert {e['provider'] for e in j['entries']} == {'Project1Service', 'Strike3'}

    j = client.get('/metadata/entries', params={'provider': 'Strike3'}).json()
    assert j['total'] == 3
    assert {e['studio'] for e in j['entries']} == {'Vixen'}

    j = client.get('/metadata/entries', params={'provider': 'Project1Service'}).json()
    assert j['total'] == 2

    assert client.get('/metadata/entries', params={'provider': 'Vixen'}).json()['total'] == 0
    assert client.get('/metadata/entries', params={'provider': 'Nope'}).json()['total'] == 0


def test_a_provider_the_registry_forgot_still_filters_to_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_scene('Some Retired Site', 'c9', 'Orphan Scene', 'Retired', '2024-06-01', 600.0)
    client = authed_client()

    j = client.get('/metadata/entries').json()
    assert j['facets']['providers'] == ['Some Retired Site']

    j = client.get('/metadata/entries', params={'provider': 'Some Retired Site'}).json()
    assert j['total'] == 1 and j['entries'][0]['title'] == 'Orphan Scene'


def test_page_offers_a_provider_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    page = authed_client().get('/metadata')
    assert 'f-provider' in page.text
    assert '>Provider<' in page.text
    assert '<option value="__manual__">Manual</option>' in page.text


def test_page_has_a_card_layout(monkeypatch: pytest.MonkeyPatch) -> None:
    page = authed_client().get('/metadata')
    assert '@media (max-width: 720px)' in page.text
    assert 'data-label="Data18"' in page.text
    assert 'class="c-title"' in page.text
    assert 'filtersToggle' in page.text
    assert '<div class="cards" id="cards"></div>' in page.text
    assert 'repeat(auto-fill, minmax(320px, 1fr))' in page.text
    assert '.cards { grid-template-columns: 1fr; }' in page.text
    assert '<table' not in page.text


def test_cards_show_genre_counts_and_actor_names(monkeypatch: pytest.MonkeyPatch) -> None:
    page = authed_client().get('/metadata')
    assert 'data-label="Genres"' in page.text
    assert 'data-label="Actors"' in page.text
    assert 'personLink(a)' in page.text
    assert 'function personLink(' in page.text
    assert "'/people/edit?' + new URLSearchParams({name}).toString()" in page.text
    assert '${e.genres || 0}' in page.text


def test_page_offers_an_actor_filter_and_bulk_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    page = authed_client().get('/metadata')
    assert 'id="f-actor"' in page.text
    assert '>Actor<' in page.text
    assert "'f-actor': 'actor'" in page.text
    assert 'refreshShown()' in page.text
    assert 'Refresh Filtered (${TOTAL})' in page.text


def test_page_has_a_mobile_sort_control(monkeypatch: pytest.MonkeyPatch) -> None:
    page = authed_client().get('/metadata')
    assert 'mobileSort' in page.text
    assert '>Sort By<' in page.text
    assert 'buildSortOptions()' in page.text
    assert 'applySortIndicators()' in page.text


def _edit_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import phoenixadult.routes.metadata_cache_routes as mcr

    monkeypatch.setattr(mcr.metadata_cache, 'load_for_edit', lambda key: {'MediaContainer': {'Metadata': [{'title': 'Scene ' + key}]}})
    return authed_client()


def test_edit_page_offers_a_refresh_button(monkeypatch: pytest.MonkeyPatch) -> None:
    page = _edit_client(monkeypatch).get('/metadata/edit?key=studio/abc')
    assert page.status_code == 200
    assert '>Refresh Metadata<' in page.text
    assert 'refreshMeta()' in page.text
    assert 'id="subKey"' in page.text


def test_refresh_queues_a_forced_rescrape(monkeypatch: pytest.MonkeyPatch) -> None:
    import phoenixadult.routes.metadata_cache_routes as mcr
    from phoenixadult.models.provider_info import ProviderInfo

    provider = ProviderInfo(id='phoenixadult', plex_identifier='tv.plex.test', title='P', version='1', media_type='movie')
    calls: dict[str, object] = {}

    class _Svc:
        def drop_memo(self, rating_key: str, prov: ProviderInfo) -> None:
            calls['dropped'] = rating_key

        def queue_snapshot(self, rating_key: str, prov: ProviderInfo, language: str | None, **kw: object) -> bool:
            calls.update({'rating_key': rating_key, **kw})
            return True

    monkeypatch.setattr(mcr, 'service_for', lambda provider_id: (provider, _Svc()))
    monkeypatch.setattr(mcr.scene_store, 'scrape_target', lambda key: {'site': 'BaDoinkVR', 'cur_id': 'abc', 'rating_key': 'scene-badoinkvr-abc'})
    monkeypatch.setattr(mcr.scene_store, 'snapshot_state', lambda site, cur_id: {'key': 'studio/abc', 'updated_at': '100.0'})

    client = authed_client()
    assert client.post('/metadata/refresh', json={}).status_code == 400

    r = client.post('/metadata/refresh', json={'key': 'studio/abc'})
    assert r.status_code == 200
    assert r.json() == {
        'ok': True,
        'queued': True,
        'site': 'BaDoinkVR',
        'cur_id': 'abc',
        'queue_key': 'phoenixadult:scene-badoinkvr-abc',
        'updated_at': '100.0',
    }
    assert calls == {'dropped': 'scene-badoinkvr-abc', 'rating_key': 'scene-badoinkvr-abc', 'force': True, 'rescrape': True}


def test_refresh_rejects_a_key_with_no_scene(monkeypatch: pytest.MonkeyPatch) -> None:
    import phoenixadult.routes.metadata_cache_routes as mcr

    monkeypatch.setattr(mcr.scene_store, 'scrape_target', lambda key: None)
    r = authed_client().post('/metadata/refresh', json={'key': 'studio/gone'})
    assert r.status_code == 404 and r.json()['ok'] is False


def test_snapshot_endpoint_tracks_a_moved_key(monkeypatch: pytest.MonkeyPatch) -> None:
    import phoenixadult.routes.metadata_cache_routes as mcr

    monkeypatch.setattr(mcr.scene_store, 'snapshot_state', lambda site, cur_id: {'key': 'NewStudio/abc', 'updated_at': '200.0'})
    monkeypatch.setattr(mcr.metadata_cache, 'load_for_edit', lambda key: {'MediaContainer': {'Metadata': [{'title': 'Renamed'}]}})
    client = authed_client()
    assert client.get('/metadata/snapshot').status_code == 400

    j = client.get('/metadata/snapshot', params={'site': 'BaDoinkVR', 'cur_id': 'abc'}).json()
    assert j == {'ok': True, 'key': 'NewStudio/abc', 'updated_at': '200.0', 'metadata': {'title': 'Renamed'}, 'locks': {'fields': [], 'imagesLocked': False}}


def test_refresh_bulk_queues_each_match(monkeypatch: pytest.MonkeyPatch) -> None:
    import phoenixadult.routes.metadata_cache_routes as mcr
    from phoenixadult.models.provider_info import ProviderInfo

    provider = ProviderInfo(id='phoenixadult', plex_identifier='tv.plex.test', title='P', version='1', media_type='movie')
    queued: list[str] = []

    class _Svc:
        def drop_memo(self, rating_key: str, prov: ProviderInfo) -> None:
            pass

        def queue_snapshot(self, rating_key: str, prov: ProviderInfo, language: str | None, **kw: object) -> bool:
            queued.append(rating_key)
            return rating_key != 'scene-badoinkvr-full'

    targets = {
        'studio/a': {'site': 'BaDoinkVR', 'cur_id': 'a', 'rating_key': 'scene-badoinkvr-a'},
        'studio/b': {'site': 'BaDoinkVR', 'cur_id': 'b', 'rating_key': 'scene-badoinkvr-full'},
    }
    monkeypatch.setattr(mcr, 'service_for', lambda provider_id: (provider, _Svc()))
    monkeypatch.setattr(mcr.scene_store, 'scrape_target', lambda key: targets.get(key))

    client = authed_client()
    assert client.post('/metadata/refresh-bulk', json={'keys': []}).status_code == 400
    assert client.post('/metadata/refresh-bulk', json={'keys': ['noslash']}).status_code == 400

    r = client.post('/metadata/refresh-bulk', json={'keys': ['studio/a', 'studio/b', 'studio/gone']})
    assert r.status_code == 200
    assert r.json() == {'ok': True, 'queued': 1, 'skipped': 2}
    assert queued == ['scene-badoinkvr-a', 'scene-badoinkvr-full']


def test_entries_endpoint_passes_the_actor_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    import phoenixadult.routes.metadata_cache_routes as mcr

    seen: dict[str, object] = {}

    def fake_page(**kw: object) -> tuple[list[dict[str, object]], int]:
        seen.update(kw)
        return [], 0

    monkeypatch.setattr(mcr.cache_listing, 'entries_page', fake_page)
    monkeypatch.setattr(mcr.cache_duplicates, 'duplicate_entries', lambda: [])
    client = authed_client()
    client.get('/metadata/entries', params={'actor': 'Jane Doe'})
    assert seen['actor'] == 'Jane Doe'


def _seed_cast(site: str, cur: str, title: str, actors: list[str], genres: list[str]) -> None:
    from phoenixadult.utils.cache import scene_store

    md = {
        'type': 'movie',
        'ratingKey': f'scene-{site.lower()}-{cur}',
        'guid': 'g',
        'title': title,
        'studio': site,
        'Role': [{'tag': name} for name in actors],
        'Genre': [{'tag': name} for name in genres],
    }
    data = {'MediaContainer': {'identifier': 'i', 'size': 1, 'Metadata': [md]}}
    scene_store.upsert(site, cur, cache_layout.scene_hash_for(site, cur), f'{site.lower()}/{cur}', data, updated_at=100.0)


def test_entries_carry_actors_and_genre_counts_and_filter_by_actor(monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_cast('Brazzers', 'x1', 'With Cast', ['Jane Doe', 'John Roe'], ['Anal', 'Blonde', 'MILF'])
    _seed_cast('Brazzers', 'x2', 'No Cast', [], ['Anal'])
    client = authed_client()

    by_title = {e['title']: e for e in client.get('/metadata/entries').json()['entries']}
    assert by_title['With Cast']['actors'] == ['Jane Doe', 'John Roe']
    assert by_title['With Cast']['genres'] == 3
    assert by_title['No Cast']['actors'] == []
    assert by_title['No Cast']['genres'] == 1

    j = client.get('/metadata/entries', params={'actor': 'jane'}).json()
    assert j['total'] == 1 and j['entries'][0]['title'] == 'With Cast'

    j = client.get('/metadata/entries', params={'actor': '__blank__'}).json()
    assert j['total'] == 1 and j['entries'][0]['title'] == 'No Cast'

    assert client.get('/metadata/entries', params={'actor': 'nobody'}).json()['total'] == 0


def test_top_bar_splits_search_filters_and_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    page = authed_client().get('/metadata')
    assert '<div class="searchbar">' in page.text
    assert '<div class="controls" id="controls">' in page.text
    assert '<div class="toolbar">' in page.text
    assert 'repeat(auto-fit, minmax(150px, 1fr))' in page.text
    assert '.controls.open .filters { display: grid; }' in page.text
    assert 'controls.classList.toggle(cls)' in page.text
    assert 'controls.classList.remove(other);' in page.text, 'one panel at a time'
    assert "function toggleActions() { return paDisclosure('actions-open', 'actionsToggle'); }" in page.text


def test_genre_filter_splits_tagged_from_untagged(monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_cast('Brazzers', 'g1', 'Has Genres', ['Jane Doe'], ['Anal', 'MILF'])
    _seed_cast('Brazzers', 'g2', 'Bare Scene', ['Jane Doe'], [])
    client = authed_client()

    j = client.get('/metadata/entries', params={'genre': '__set__'}).json()
    assert j['total'] == 1 and j['entries'][0]['title'] == 'Has Genres'

    j = client.get('/metadata/entries', params={'genre': '__blank__'}).json()
    assert j['total'] == 1 and j['entries'][0]['title'] == 'Bare Scene'

    assert client.get('/metadata/entries').json()['total'] == 2


def test_actor_suggestions_match_and_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_cast('Brazzers', 's1', 'One', ['Jane Doe', 'Janet Rowe'], ['Anal'])
    _seed_cast('Brazzers', 's2', 'Two', ['John Roe', 'Jane Doe'], ['Anal'])
    assert TestClient(create_app()).get('/metadata/actors', headers={'accept': 'application/json'}).status_code == 401
    client = authed_client()

    everyone = client.get('/metadata/actors').json()['actors']
    assert everyone == ['Jane Doe', 'Janet Rowe', 'John Roe']

    assert client.get('/metadata/actors', params={'q': 'jan'}).json()['actors'] == ['Jane Doe', 'Janet Rowe']
    assert client.get('/metadata/actors', params={'q': 'roe'}).json()['actors'] == ['John Roe']
    assert client.get('/metadata/actors', params={'q': 'ow'}).json()['actors'] == ['Janet Rowe']
    assert client.get('/metadata/actors', params={'limit': 1}).json()['actors'] == ['Jane Doe']
    assert client.get('/metadata/actors', params={'q': 'nobody'}).json()['actors'] == []


def test_page_wires_the_actor_autocomplete_and_genre_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    page = authed_client().get('/metadata')
    assert 'list="actor-options"' in page.text
    assert '<datalist id="actor-options"></datalist>' in page.text
    assert 'actorChanged()' in page.text
    assert "fetch('/metadata/actors?'" in page.text
    assert 'id="f-genre"' in page.text
    assert '<option value="__set__">Tagged</option>' in page.text
    assert '<option value="__blank__">Untagged</option>' in page.text
    assert "'f-genre': 'genre'" in page.text


def test_edit_page_stops_waiting_when_the_job_leaves_the_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    page = _edit_client(monkeypatch).get('/metadata/edit?key=studio/abc')
    assert 'REFRESH_SETTLE_MS' in page.text
    assert "return 'unchanged'" in page.text
    assert 'The scrape finished without changing this snapshot' in page.text


def _seed_faceted(site: str, cur: str, title: str, studio: str, tagline: str, date: str) -> None:
    from phoenixadult.utils.cache import scene_store

    md = {'type': 'movie', 'ratingKey': f'rk-{cur}', 'guid': 'g', 'title': title, 'studio': studio, 'tagline': tagline, 'originallyAvailableAt': date}
    scene_store.upsert(
        site,
        cur,
        cache_layout.scene_hash_for(site, cur),
        f'{studio}/{cur}',
        {'MediaContainer': {'identifier': 'i', 'size': 1, 'Metadata': [md]}},
        updated_at=100.0,
    )


def test_facets_narrow_to_the_other_active_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_faceted('Brazzers', 'f1', 'A', 'Brazzers', 'Real Wife Stories', '2024-01-05')
    _seed_faceted('Brazzers', 'f2', 'B', 'Brazzers', 'Mom Ok', '2023-06-11')
    _seed_faceted('Vixen', 'f3', 'C', 'Vixen', 'Blacked', '2022-03-02')
    client = authed_client()

    wide = client.get('/metadata/entries').json()
    assert wide['studios'] == ['Brazzers', 'Vixen']
    assert wide['facets']['taglines'] == ['Blacked', 'Mom Ok', 'Real Wife Stories']
    assert wide['facets']['years'] == ['2024', '2023', '2022']

    narrow = client.get('/metadata/entries', params={'studio': 'Brazzers'}).json()
    assert narrow['facets']['taglines'] == ['Mom Ok', 'Real Wife Stories']
    assert narrow['facets']['years'] == ['2024', '2023']
    assert narrow['studios'] == ['Brazzers', 'Vixen']

    by_year = client.get('/metadata/entries', params={'year': '2022'}).json()
    assert by_year['studios'] == ['Vixen']
    assert by_year['facets']['taglines'] == ['Blacked']
    assert by_year['facets']['years'] == ['2024', '2023', '2022']


def _seed_people(cur: str, title: str, roles: list[str], directors: list[str], collections: list[str]) -> None:
    from phoenixadult.utils.cache import scene_store

    md: dict[str, object] = {'type': 'movie', 'ratingKey': f'rk-{cur}', 'guid': 'g', 'title': title, 'studio': 'Brazzers'}
    if roles:
        md['Role'] = [{'tag': r} for r in roles]
    if directors:
        md['Director'] = [{'tag': d} for d in directors]
    if collections:
        md['Collection'] = [{'tag': c} for c in collections]
    scene_store.upsert(
        'Brazzers',
        cur,
        cache_layout.scene_hash_for('Brazzers', cur),
        f'people/{cur}',
        {'MediaContainer': {'identifier': 'i', 'size': 1, 'Metadata': [md]}},
        updated_at=100.0,
    )


def test_blank_filters_find_snapshots_missing_people_and_collections(monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_people('pp1', 'Full', ['Jane Doe'], ['A Director'], ['RWS'])
    _seed_people('pp2', 'No Cast', [], ['A Director'], ['RWS'])
    _seed_people('pp3', 'Bare', [], [], [])
    client = authed_client()

    def titles(**params: str) -> list[str]:
        return sorted(e['title'] for e in client.get('/metadata/entries', params=params).json()['entries'])

    assert titles(cast='__blank__') == ['Bare', 'No Cast']
    assert titles(cast='__set__') == ['Full']
    assert titles(director='__blank__') == ['Bare']
    assert titles(producer='__blank__') == ['Bare', 'Full', 'No Cast']
    assert titles(collection='__blank__') == ['Bare']
    assert titles(cast='__blank__', collection='__blank__') == ['Bare']


def test_page_offers_blank_options_for_people_and_lists_them_first(monkeypatch: pytest.MonkeyPatch) -> None:
    page = authed_client().get('/metadata')
    for fid in ('f-cast', 'f-director', 'f-producer'):
        assert f'id="{fid}"' in page.text
    assert page.text.count('<option value="__blank__">Uncredited</option>') == 3
    assert "'f-cast': 'cast'" in page.text
    blank_first = page.text.index("o.value = '__blank__'") < page.text.index('spec.values.forEach')
    assert blank_first


def test_both_screens_offer_sfw_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _edit_client(monkeypatch)

    listing = client.get('/metadata')
    assert 'id="sfwToggle"' in listing.text
    assert "const SFW_KEY = 'metadata-sfw';" in listing.text
    assert 'toggleSfw()' in listing.text
    assert "const thumb = SFW\n          ? ''" in listing.text
    assert 'Hidden' not in listing.text

    editor = client.get('/metadata/edit?key=studio/abc')
    assert 'id="sfwToggle"' in editor.text
    assert "const SFW_KEY = 'metadata-sfw';" in editor.text
    assert 'if (!SFW) {\n          const preview' in editor.text
    assert 'hidden-shot' not in editor.text
    assert 'paintSfwToggle();\n    installLockUI();\n    load();' in editor.text


async def test_edit_page_shows_the_mapping_slug(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    from phoenixadult.models.metadata import PlexMetadataResponse
    from phoenixadult.utils.cache import metadata as mc

    resp = PlexMetadataResponse.model_validate(
        {
            'MediaContainer': {
                'identifier': 'i',
                'size': 1,
                'Metadata': [{'type': 'movie', 'ratingKey': 'rk', 'guid': 'g', 'title': 'Cool Scene', 'studio': 'MYLF', 'tagline': 'MYLF Features'}],
            }
        }
    )
    assert await mc.write('MYLF', 'slug1', resp) is True
    key = cache_listing.entries()[0]['key']

    body = authed_client().get(f'/metadata/edit?key={key}').text
    assert '"cool-scene-mylffeatures"' in body
    assert 'id="d18slug"' in body
    assert 'id="d18slugCopy"' in body


async def test_entries_endpoint_filters_potential_duplicates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    from phoenixadult.models.metadata import PlexMetadataResponse
    from phoenixadult.utils.cache import metadata as mc

    def resp(title: str, tagline: str) -> PlexMetadataResponse:
        return PlexMetadataResponse.model_validate(
            {
                'MediaContainer': {
                    'identifier': 'i',
                    'size': 1,
                    'Metadata': [
                        {
                            'type': 'movie',
                            'ratingKey': 'rk',
                            'guid': 'g',
                            'title': title,
                            'studio': 'MYLF',
                            'tagline': tagline,
                            'originallyAvailableAt': '2024-01-05',
                        }
                    ],
                }
            }
        )

    assert await mc.write('MYLF', 'q1', resp('Twin Peaks!', 'Mylf Wood')) is True
    assert await mc.write('MYLF', 'q2', resp('twin peaks', 'MylfWood')) is True
    assert await mc.write('MYLF', 'q3', resp('Unrelated Scene', 'Mylf Wood')) is True

    client = authed_client()
    everything = client.get('/metadata/entries').json()
    assert everything['total'] == 3
    dups = client.get('/metadata/entries?dups=2').json()
    assert dups['total'] == 2
    assert {e['title'] for e in dups['entries']} == {'Twin Peaks!', 'twin peaks'}


def _source_client(monkeypatch: pytest.MonkeyPatch, cur_id: str, site: str = 'Vixen') -> TestClient:
    import phoenixadult.routes.metadata_cache_routes as mcr

    monkeypatch.setattr(mcr.metadata_cache, 'load_for_edit', lambda key: {'MediaContainer': {'Metadata': [{'title': 'Scene ' + key}]}})
    monkeypatch.setattr(mcr.scene_store, 'identity_for', lambda key: (site, cur_id))
    return authed_client()


def test_edit_page_links_to_the_source_scene(monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.utils.helpers.ids import pack_cur_id

    cur = pack_cur_id(['https://example.com/scene/alpha', '2024-01-01'])
    page = _source_client(monkeypatch, cur).get('/metadata/edit?key=studio/abc')
    assert 'id="sourceLink"' in page.text
    assert 'href="https://example.com/scene/alpha"' in page.text
    assert 'Scene ↗' in page.text
    assert 'id="sourcePanel"' not in page.text


def test_edit_page_labels_a_listing_link(monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.utils.helpers.ids import pack_cur_id

    cur = pack_cur_id(['someslug', '2019-04-12', 'https://sheisnerdy.com/detailed/3'])
    page = _source_client(monkeypatch, cur, site='She Is Nerdy').get('/metadata/edit?key=studio/abc')
    assert 'Listing ↗' in page.text
    assert 'href="https://sheisnerdy.com/detailed/3"' in page.text


def test_edit_page_shows_the_source_json_panel(monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    from phoenixadult.utils.helpers.ids import b64url_encode

    cur = b64url_encode(json.dumps({'title': 'Embedded', 'summary': 'words'}))
    page = _source_client(monkeypatch, cur).get('/metadata/edit?key=studio/abc')
    assert 'id="sourcePanel"' in page.text
    assert 'Source JSON' in page.text
    assert 'var SOURCE_JSON' in page.text
    assert 'id="sourceLink"' not in page.text


def test_edit_page_links_and_panels_a_blob_with_a_url(monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    from phoenixadult.utils.helpers.ids import b64url_encode

    cur = b64url_encode(json.dumps({'movieURL': 'https://www.adultempire.com/1/m.html', 'sceneNum': 2}))
    page = _source_client(monkeypatch, cur).get('/metadata/edit?key=studio/abc')
    assert 'id="sourceLink"' in page.text and 'id="sourcePanel"' in page.text


def test_edit_page_hides_source_ui_for_an_undecodable_id(monkeypatch: pytest.MonkeyPatch) -> None:
    page = _source_client(monkeypatch, 'cur1').get('/metadata/edit?key=studio/abc')
    assert 'id="sourceLink"' not in page.text and 'id="sourcePanel"' not in page.text


def test_source_json_validates_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    import phoenixadult.routes.metadata_cache_routes as mcr

    client = authed_client()
    assert client.get('/metadata/source-json?key=nope').status_code == 400
    monkeypatch.setattr(mcr.scene_store, 'identity_for', lambda key: None)
    assert client.get('/metadata/source-json?key=studio/gone').status_code == 404


def test_source_json_serves_an_embedded_blob_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    import phoenixadult.routes.metadata_cache_routes as mcr
    from phoenixadult.utils.helpers.ids import b64url_encode

    blob = {'title': 'Embedded', 'poster': '/img/x.jpg'}
    monkeypatch.setattr(mcr.scene_store, 'identity_for', lambda key: ('Vixen', b64url_encode(json.dumps(blob))))
    r = authed_client().get('/metadata/source-json?key=studio/abc')
    assert r.status_code == 200 and r.json() == {'ok': True, 'json': blob}


def test_source_json_proxies_an_api_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    import phoenixadult.routes.metadata_cache_routes as mcr
    from phoenixadult.utils.helpers.ids import pack_cur_id

    monkeypatch.setattr(mcr.scene_store, 'identity_for', lambda key: ('Vixen', pack_cur_id(['https://api.example.com/scenes/1'])))

    async def _ok(url: str) -> str:
        return url

    class _Stub:
        async def fetch_json(self, url: str) -> dict[str, int]:
            return {'a': 1}

    monkeypatch.setattr(mcr, 'ensure_fetchable_url', _ok)
    monkeypatch.setattr(mcr, 'get_client', lambda scraper_type: _Stub())
    r = authed_client().get('/metadata/source-json?key=studio/abc')
    assert r.status_code == 200 and r.json() == {'ok': True, 'json': {'a': 1}}


def test_source_json_refuses_a_blocked_host(monkeypatch: pytest.MonkeyPatch) -> None:
    import phoenixadult.routes.metadata_cache_routes as mcr
    from phoenixadult.utils.helpers.ids import pack_cur_id

    monkeypatch.setattr(mcr.scene_store, 'identity_for', lambda key: ('Vixen', pack_cur_id(['https://127.0.0.1/api/x'])))
    r = authed_client().get('/metadata/source-json?key=studio/abc')
    assert r.status_code == 400 and r.json()['ok'] is False


def test_source_json_rejects_a_plain_scene_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    import phoenixadult.routes.metadata_cache_routes as mcr
    from phoenixadult.utils.helpers.ids import pack_cur_id

    monkeypatch.setattr(mcr.scene_store, 'identity_for', lambda key: ('Vixen', pack_cur_id(['https://example.com/scene/alpha'])))
    r = authed_client().get('/metadata/source-json?key=studio/abc')
    assert r.status_code == 400 and 'no source payload' in r.json()['error']


def _stored_source_client(monkeypatch: pytest.MonkeyPatch, source: dict[str, object]) -> TestClient:
    import phoenixadult.routes.metadata_cache_routes as mcr

    payload = {'MediaContainer': {'Metadata': [{'title': 'Stored', 'sourceRef': source}]}}
    monkeypatch.setattr(mcr.metadata_cache, 'load_for_edit', lambda key: payload)
    monkeypatch.setattr(mcr.scene_store, 'identity_for', lambda key: ('Vixen', 'cur1'))
    return authed_client()


def test_the_stored_source_beats_the_cur_id_heuristic(monkeypatch: pytest.MonkeyPatch) -> None:
    source = {'url': 'https://www.teamskeet.com/movies/alpha', 'kind': 'page'}
    page = _stored_source_client(monkeypatch, source).get('/metadata/edit?key=studio/abc')
    assert 'href="https://www.teamskeet.com/movies/alpha"' in page.text
    assert 'Scene ↗' in page.text


def test_a_stored_listing_source_keeps_its_label_and_panel(monkeypatch: pytest.MonkeyPatch) -> None:
    source = {'url': 'https://sheisnerdy.com/detailed/3', 'kind': 'listing', 'data': {'title': 'Card'}}
    page = _stored_source_client(monkeypatch, source).get('/metadata/edit?key=studio/abc')
    assert 'Listing ↗' in page.text
    assert 'id="sourcePanel"' in page.text


def test_a_stored_api_source_renders_the_panel_inline(monkeypatch: pytest.MonkeyPatch) -> None:
    source = {'url': 'https://example.com/api/releases/alpha', 'kind': 'api', 'data': {'id': 9}}
    page = _stored_source_client(monkeypatch, source).get('/metadata/edit?key=studio/abc')
    assert 'id="sourcePanel"' in page.text
    assert 'id="sourceLink"' not in page.text


def test_source_json_prefers_the_stored_data(monkeypatch: pytest.MonkeyPatch) -> None:
    source = {'url': 'https://example.com/api/releases/alpha', 'kind': 'api', 'data': {'id': 9}}
    r = _stored_source_client(monkeypatch, source).get('/metadata/source-json?key=studio/abc')
    assert r.status_code == 200 and r.json() == {'ok': True, 'json': {'id': 9}}


def test_cards_show_two_actors_and_expand_the_rest() -> None:
    page = authed_client().get('/metadata')
    assert 'cast.slice(0, 2)' in page.text
    assert 'class="c-rest" hidden' in page.text
    assert 'class="c-more" aria-expanded="false"' in page.text
    assert "const more = e.target.closest('.c-more');" in page.text


def test_the_empty_thumbnail_is_a_centred_well() -> None:
    page = authed_client().get('/metadata')
    rule = page.text.split('\n    .card .noimg {')[1].split('}')[0]
    assert 'place-content: center' in rule
    assert 'font-size: var(--text-sm)' in rule
    assert 'checkerboard-a' in rule
    assert '.card .noimg::before' not in page.text
    assert '>No image<' in page.text


def test_the_card_subgrid_span_matches_its_row_count() -> None:
    import re

    page = authed_client().get('/metadata').text
    block = page.split('return `<div class="card">')[1].split('</div>`;')[0]
    rows = len([ln for ln in block.split('\n') if re.match(r'^ {10}(<div|\$\{)', ln)])
    assert f'grid-row: span {rows};' in page
    assert f'.cards.sfw .card {{ grid-row: span {rows - 1}; }}' in page
    assert "cards.classList.toggle('sfw', SFW);" in page
    assert 'const actors = `<div class="c-actors"' in page


def test_every_action_button_uses_the_shared_button_system() -> None:
    import re

    page = authed_client().get('/metadata').text
    for bespoke in ('edit-btn', 'purge-btn', 'export-btn', 'refresh-btn', 'dup-toggle', 'dup-btn', 'prune-btn'):
        assert bespoke not in page, f'{bespoke} should be a .pa-btn modifier now'
    ids = dict(re.findall(r'<button[^>]*class="([^"]+)"[^>]*id="([^"]+)"', page))
    for classes, button_id in ids.items():
        if button_id in ('filtersToggle',):
            continue
        assert classes.startswith('pa-btn'), f'{button_id} is not on the shared button system'


def test_the_editor_carries_a_data18_launch_point(monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.utils.helpers.ids import pack_cur_id

    page = _source_client(monkeypatch, pack_cur_id(['https://example.com/scene/alpha', '2024-01-01'])).get('/metadata/edit?key=studio/abc')
    assert 'id="data18Link"' in page.text
    assert "'https://www.data18.com/' + (qs('f-data18Type').value === 'movie' ? 'movies' : 'scenes') + '/' + id" in page.text
    assert 'hidden>Data18 ↗</a>' in page.text, 'the link starts hidden and is shown only once an id is present'


def test_the_edit_button_opens_a_new_tab_and_carries_the_page_back(monkeypatch: pytest.MonkeyPatch) -> None:
    page = _source_client(monkeypatch, 'x').get('/metadata').text
    assert "window.open('/metadata/edit?'" in page, 'edit must open a new tab, not navigate the list away'
    assert 'back: String(offset)' in page
    assert "parseInt(new URLSearchParams(location.search).get('offset')" in page, 'the list must restore the offset it was sent back to'


def test_save_and_cancel_close_the_tab_the_list_opened(monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.utils.helpers.ids import pack_cur_id

    page = _source_client(monkeypatch, pack_cur_id(['https://example.com/scene/alpha'])).get('/metadata/edit?key=studio/abc').text
    assert 'window.close()' in page
    assert 'opener.refreshEntries()' in page, 'the list behind the tab should show the edit without a full reload'
    assert "'/metadata?offset=' + encodeURIComponent(back)" in page, 'a directly-opened editor still needs somewhere to go'
    assert 'onclick="leave()"' in page


def test_the_editor_tab_is_opened_so_it_can_close_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    page = _source_client(monkeypatch, 'x').get('/metadata').text
    assert "'_blank');" in page, 'noopener would leave window.opener null, and a tab without an opener cannot close itself'


def test_the_missing_image_filter_is_offered_and_sent_to_the_server(monkeypatch: pytest.MonkeyPatch) -> None:
    page = _source_client(monkeypatch, 'x').get('/metadata').text
    assert 'id="brokenToggle"' in page
    assert "p.set('broken', '1')" in page
