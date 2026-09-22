from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.networks.metart import MetArtClient
from phoenixadult.models.scrape import SearchResult
from phoenixadult.registry import find_site
from tests.support import search_context

SITE = find_site('MetArt')
assert SITE is not None


@respx.mock
async def test_search() -> None:
    url = 'https://www.metart.com/api/search-results?query[contentType]=movies&searchPhrase=cool+scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            json={'items': [{'item': {'name': 'Cool Scene', 'path': '/movies/2021-03-04/cool-scene', 'publishedAt': '2021-03-04T00:00:00Z'}}]},
        )
    )
    results: list[SearchResult] = []
    await MetArtClient().search(results, search_context(SITE, 'cool scene'))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://www.metart.com/api/movie?name=cool-scene&date=2021-03-04'
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_detail() -> None:
    url = 'https://www.metart.com/api/movie?name=cool-scene&date=2021-03-04'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            json={
                'name': 'Cool Scene',
                'description': 'A summary.',
                'publishedAt': '2021-03-04T00:00:00Z',
                'tags': ['glamour', 'solo girl'],
                'models': [{'name': 'Jane Doe', 'headshotImagePath': '/h/jane.jpg'}],
                'photographers': [{'name': 'Some Photog'}],
                'siteUUID': 'uuid-123',
                'coverImagePath': '/cover.jpg',
                'splashImagePath': '/splash.jpg',
            },
        )
    )
    detail = await MetArtClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'MetArt'
    assert detail.tagline == 'MetArt'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Glamour', 'Solo Girl', 'Glamorous']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://www.metart.com/h/jane.jpg'
    assert detail.directors is not None and detail.directors[0].name == 'Some Photog'
    assert detail.art == [
        'https://cdn.metartnetwork.com/uuid-123/cover.jpg',
        'https://cdn.metartnetwork.com/uuid-123/splash.jpg',
    ]
