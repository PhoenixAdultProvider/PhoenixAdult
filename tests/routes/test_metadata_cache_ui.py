from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app


def test_requires_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    client = TestClient(create_app())
    assert client.get('/metadata').status_code == 401
    page = client.get('/metadata?token=tok')
    assert page.status_code == 200
    assert 'Snapshot Metadata Cache' in page.text


def test_purge_validates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    client = TestClient(create_app())
    hdr = {'x-admin-token': 'tok'}
    assert client.post('/metadata/purge', json={}, headers=hdr).status_code == 400
    r = client.post('/metadata/purge', json={'key': 'nope/abc'}, headers=hdr)
    assert r.status_code == 200 and r.json()['ok'] is False


def test_purge_bulk_validates_and_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    import phoenixadult.routes.metadata_cache_routes as mcr

    purged: list[str] = []

    def fake_purge(key: str) -> bool:
        purged.append(key)
        return key != 'studio/missing'

    monkeypatch.setattr(mcr.metadata_cache, 'purge', fake_purge)
    client = TestClient(create_app())
    hdr = {'x-admin-token': 'tok'}
    assert client.post('/metadata/purge-bulk', json={}, headers=hdr).status_code == 400
    assert client.post('/metadata/purge-bulk', json={'keys': []}, headers=hdr).status_code == 400
    assert client.post('/metadata/purge-bulk', json={'keys': 'studio/abc'}, headers=hdr).status_code == 400
    assert client.post('/metadata/purge-bulk', json={'keys': ['noslash']}, headers=hdr).status_code == 400
    assert client.post('/metadata/purge-bulk', json={'keys': ['studio/abc', 5]}, headers=hdr).status_code == 400
    assert purged == []

    r = client.post('/metadata/purge-bulk', json={'keys': ['studio/abc', 'studio/missing', 'studio/sub/def']}, headers=hdr)
    assert r.status_code == 200 and r.json() == {'ok': True, 'purged': 2}
    assert purged == ['studio/abc', 'studio/missing', 'studio/sub/def']


def test_page_has_filtered_bulk_purge(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    import phoenixadult.routes.metadata_cache_routes as mcr

    monkeypatch.setattr(mcr.metadata_cache, 'duplicate_entries', lambda: [])
    monkeypatch.setattr(mcr.metadata_cache, 'entries', lambda: [])
    page = TestClient(create_app()).get('/metadata?token=tok')
    assert 'purgeShown()' in page.text
    assert 'This cannot be undone.' in page.text
    assert 'exportShown()' in page.text
    assert 'f-data18' in page.text
    assert 'data18_manual_mappings${suffix}.json' in page.text


def test_state_and_entries_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    import phoenixadult.routes.metadata_cache_routes as mcr

    monkeypatch.setattr(mcr.metadata_cache, 'change_token', lambda: '3:123.0')
    monkeypatch.setattr(mcr.metadata_cache, 'entries_page', lambda **_kw: ([{'key': 'studio/abc'}], 1))
    monkeypatch.setattr(mcr.metadata_cache, 'duplicate_entries', lambda: ['studio/abc'])
    monkeypatch.setattr(mcr.metadata_cache, 'studios', lambda: ['Studio'])
    monkeypatch.setattr(mcr.metadata_cache, 'facets', lambda: {'taglines': ['T']})
    client = TestClient(create_app())
    assert client.get('/metadata/state').status_code == 401
    hdr = {'x-admin-token': 'tok'}
    assert client.get('/metadata/state', headers=hdr).json() == {'token': '3:123.0'}
    assert client.get('/metadata/entries', headers=hdr).json() == {
        'entries': [{'key': 'studio/abc'}],
        'dup_keys': ['studio/abc'],
        'total': 1,
        'studios': ['Studio'],
        'facets': {'taglines': ['T']},
    }


def test_page_persists_filters_and_polls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    import phoenixadult.routes.metadata_cache_routes as mcr

    monkeypatch.setattr(mcr.metadata_cache, 'duplicate_entries', lambda: [])
    monkeypatch.setattr(mcr.metadata_cache, 'entries', lambda: [])
    page = TestClient(create_app()).get('/metadata?token=tok')
    assert 'metadata-cache-filters' in page.text
    assert 'restoreFilters()' in page.text
    assert "fetch('/metadata/state'" in page.text
    assert 'setInterval(pollState' in page.text


def test_page_injects_duplicate_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    import phoenixadult.routes.metadata_cache_routes as mcr

    monkeypatch.setattr(mcr.metadata_cache, 'duplicate_entries', lambda: ['a/b/c', 'd/e/f'])
    monkeypatch.setattr(mcr.metadata_cache, 'entries', lambda: [])
    page = TestClient(create_app()).get('/metadata?token=tok')
    assert 'const DUP_KEYS = ["a/b/c", "d/e/f"];' in page.text
    assert 'Show Duplicates' in page.text


def test_page_has_server_side_pagination(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    page = TestClient(create_app()).get('/metadata?token=tok')
    assert 'let TOTAL = 0;' in page.text
    assert 'let STUDIOS = [];' in page.text
    assert 'serverQuery(PAGE_SIZE, true)' in page.text
    assert '>Previous<' in page.text and '>Next<' in page.text


def _seed_scene(site: str, cur: str, title: str, studio: str, date: str, updated: float) -> None:
    from phoenixadult.utils import cache as mc
    from phoenixadult.utils.cache import scene_store

    data = {
        'MediaContainer': {
            'identifier': 'i',
            'size': 1,
            'Metadata': [{'type': 'movie', 'ratingKey': 'rk', 'guid': 'g', 'title': title, 'studio': studio, 'originallyAvailableAt': date}],
        }
    }
    scene_store.upsert(site, cur, mc._hash(site, cur), f'{studio.lower()}/{cur}', data, updated_at=updated)


def _seed_library() -> None:
    _seed_scene('Brazzers', 'c1', 'Alpha Scene', 'Brazzers', '2024-01-01', 100.0)
    _seed_scene('Brazzers', 'c2', 'Bravo Scene', 'Brazzers', '2024-02-01', 200.0)
    _seed_scene('Vixen', 'c3', 'Charlie Night', 'Vixen', '2024-03-01', 300.0)
    _seed_scene('Vixen', 'c4', 'Delta Night', 'Vixen', '2024-04-01', 400.0)
    _seed_scene('Vixen', 'c5', 'Echo Scene', 'Vixen', '2024-05-01', 500.0)


def test_entries_endpoint_filters_sorts_and_paginates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    _seed_library()
    client = TestClient(create_app())
    hdr = {'x-admin-token': 'tok'}

    j = client.get('/metadata/entries', headers=hdr).json()
    assert j['total'] == 5 and len(j['entries']) == 5
    assert [e['title'] for e in j['entries']] == ['Echo Scene', 'Delta Night', 'Charlie Night', 'Bravo Scene', 'Alpha Scene']
    assert j['studios'] == ['Brazzers', 'Vixen']
    assert j['dup_keys'] == []

    j = client.get('/metadata/entries', headers=hdr, params={'studio': 'Brazzers'}).json()
    assert j['total'] == 2
    assert {e['studio'] for e in j['entries']} == {'Brazzers'}

    j = client.get('/metadata/entries', headers=hdr, params={'q': 'night'}).json()
    assert j['total'] == 2
    assert sorted(e['title'] for e in j['entries']) == ['Charlie Night', 'Delta Night']

    j = client.get('/metadata/entries', headers=hdr, params={'sort': 'title', 'dir': 'asc'}).json()
    assert [e['title'] for e in j['entries']] == ['Alpha Scene', 'Bravo Scene', 'Charlie Night', 'Delta Night', 'Echo Scene']

    j = client.get('/metadata/entries', headers=hdr, params={'sort': 'release_date', 'dir': 'desc'}).json()
    assert [e['date'] for e in j['entries']] == ['2024-05-01', '2024-04-01', '2024-03-01', '2024-02-01', '2024-01-01']

    j = client.get('/metadata/entries', headers=hdr, params={'sort': 'title', 'dir': 'asc', 'limit': 2, 'offset': 2}).json()
    assert j['total'] == 5
    assert [e['title'] for e in j['entries']] == ['Charlie Night', 'Delta Night']

    j = client.get('/metadata/entries', headers=hdr, params={'sort': 'bogus', 'dir': 'sideways'}).json()
    assert [e['title'] for e in j['entries']][0] == 'Echo Scene'

    j = client.get('/metadata/entries', headers=hdr, params={'studio': 'Brazzers', 'q': 'alpha'}).json()
    assert j['total'] == 1 and j['entries'][0]['title'] == 'Alpha Scene'


def test_entries_facet_filters_paginate_consistently(monkeypatch: pytest.MonkeyPatch) -> None:
    """Facet filters run in SQL, so a filtered page total matches the page contents
    (the old client-side facets produced 138-of-500-page style mismatches)."""
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    _seed_library()
    client = TestClient(create_app())
    hdr = {'x-admin-token': 'tok'}

    j = client.get('/metadata/entries', headers=hdr, params={'year': '2024', 'month': '03'}).json()
    assert j['total'] == 1 and j['entries'][0]['title'] == 'Charlie Night'

    j = client.get('/metadata/entries', headers=hdr, params={'year': '2024', 'limit': 2, 'offset': 2}).json()
    assert j['total'] == 5 and len(j['entries']) == 2

    j = client.get('/metadata/entries', headers=hdr, params={'tagline': '__blank__'}).json()
    assert j['total'] == 5

    j = client.get('/metadata/entries', headers=hdr, params={'data18': '__set__'}).json()
    assert j['total'] == 0

    j = client.get('/metadata/entries', headers=hdr, params={'limit': 0}).json()
    assert j['total'] == 5 and len(j['entries']) == 5

    facets = j['facets']
    assert facets['years'] == ['2024']
    assert facets['months'] == ['01', '02', '03', '04', '05']
    assert facets['tagline_blank'] is True


def test_entries_filter_by_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    _seed_library()
    client = TestClient(create_app())
    hdr = {'x-admin-token': 'tok'}

    j = client.get('/metadata/entries', headers=hdr).json()
    assert j['facets']['providers'] == ['Project1Service', 'Strike3']
    assert {e['provider'] for e in j['entries']} == {'Project1Service', 'Strike3'}

    j = client.get('/metadata/entries', headers=hdr, params={'provider': 'Strike3'}).json()
    assert j['total'] == 3
    assert {e['studio'] for e in j['entries']} == {'Vixen'}

    j = client.get('/metadata/entries', headers=hdr, params={'provider': 'Project1Service'}).json()
    assert j['total'] == 2

    assert client.get('/metadata/entries', headers=hdr, params={'provider': 'Vixen'}).json()['total'] == 0
    assert client.get('/metadata/entries', headers=hdr, params={'provider': 'Nope'}).json()['total'] == 0


def test_a_provider_the_registry_forgot_still_filters_to_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    _seed_scene('Some Retired Site', 'c9', 'Orphan Scene', 'Retired', '2024-06-01', 600.0)
    client = TestClient(create_app())
    hdr = {'x-admin-token': 'tok'}

    j = client.get('/metadata/entries', headers=hdr).json()
    assert j['facets']['providers'] == ['Some Retired Site']

    j = client.get('/metadata/entries', headers=hdr, params={'provider': 'Some Retired Site'}).json()
    assert j['total'] == 1 and j['entries'][0]['title'] == 'Orphan Scene'


def test_page_offers_a_provider_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    page = TestClient(create_app()).get('/metadata?token=tok')
    assert 'f-provider' in page.text
    assert '>Provider<' in page.text
    assert '<option value="__manual__">Manual</option>' in page.text


def test_page_has_a_mobile_card_layout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    page = TestClient(create_app()).get('/metadata?token=tok')
    assert '@media (max-width: 720px)' in page.text
    assert 'data-label="Data18"' in page.text
    assert 'class="c-title"' in page.text
    assert 'filtersToggle' in page.text
    assert 'tbody td:has(> .blank) { display: none; }' in page.text


def test_page_has_a_mobile_sort_control(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ADMIN_TOKEN', 'tok')
    page = TestClient(create_app()).get('/metadata?token=tok')
    assert 'mobileSort' in page.text
    assert '>Sort By<' in page.text
    assert 'buildSortOptions()' in page.text
    assert 'applySortIndicators()' in page.text
