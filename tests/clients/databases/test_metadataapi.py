from __future__ import annotations

from urllib.parse import quote

import httpx
import respx

from app.clients.aggregators.metadataapi import MetadataAPIClient
from app.clients.base import SearchContext, SearchResult
from app.registry import find_site

SITE = find_site('MetadataAPI')
assert SITE is not None
DETAIL_URL = 'https://api.theporndb.net/scenes/sc1'


@respx.mock
async def test_search() -> None:
    respx.get('https://api.theporndb.net/scenes?parse=' + quote('some scene')).mock(
        return_value=httpx.Response(200, json={'data': [{'_id': 'sc1', 'title': 'Some Scene', 'site': {'name': 'Brazzers'}}]})
    )
    results: list[SearchResult] = []
    await MetadataAPIClient().search(results, SearchContext(title='some scene', encoded=quote('some scene'), search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Some Scene'
    assert results[0].scene_url == 'https://api.theporndb.net/scenes/sc1'
    assert results[0].subsite == 'Brazzers'


@respx.mock
async def test_detail_parent_network() -> None:
    respx.get(DETAIL_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                'data': {
                    'title': 'Some Scene',
                    'description': 'A scene.',
                    'date': '2024-01-05T00:00:00Z',
                    'site': {'id': 5, 'name': 'Brazzers', 'network_id': 9},
                    'tags': [{'name': 'Anal'}, {'name': 'Blonde'}],
                    'performers': [{'name': 'Jane Doe', 'face': 'https://cdn.tpdb.net/jane.jpg'}],
                    'posters': {'large': 'https://cdn.tpdb.net/poster.jpg'},
                    'background': {'large': 'https://cdn.tpdb.net/bg.jpg'},
                }
            },
        )
    )
    respx.get('https://api.theporndb.net/sites/9').mock(return_value=httpx.Response(200, json={'data': {'name': 'Brazzers Network'}}))
    detail = await MetadataAPIClient().fetch_scene_detail(DETAIL_URL, SITE)
    assert detail is not None
    assert detail.title == 'Some Scene'
    assert detail.summary == 'A scene.'
    assert detail.studio == 'Brazzers Network'
    assert detail.tagline is None
    assert detail.collections == ['Brazzers', 'Brazzers Network']
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['Anal', 'Blonde']
    assert [(a.name, a.photo_url) for a in detail.actors] == [('Jane Doe', 'https://cdn.tpdb.net/jane.jpg')]
    assert detail.art == ['https://cdn.tpdb.net/poster.jpg', 'https://cdn.tpdb.net/bg.jpg']


@respx.mock
async def test_detail_performer_parent_override() -> None:
    respx.get(DETAIL_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                'data': {
                    'title': 'X',
                    'site': {'id': 5, 'name': 'Brazzers'},
                    'performers': [
                        {
                            'name': 'Alias Name',
                            'face': 'https://cdn.tpdb.net/default.png',
                            'parent': {'name': 'Real Name', 'face': 'https://cdn.tpdb.net/real.jpg'},
                        }
                    ],
                }
            },
        )
    )
    detail = await MetadataAPIClient().fetch_scene_detail(DETAIL_URL, SITE)
    assert detail is not None
    assert detail.studio == 'Brazzers'
    assert [(a.name, a.photo_url) for a in detail.actors] == [('Real Name', 'https://cdn.tpdb.net/real.jpg')]
