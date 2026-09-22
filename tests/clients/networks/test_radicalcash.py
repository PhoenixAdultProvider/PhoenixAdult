from __future__ import annotations

import json

import httpx
import respx

from phoenixadult.clients.networks.radicalcash import RadicalCashClient
from phoenixadult.models.scrape import SearchResult
from phoenixadult.registry import find_site
from tests.support import search_context

SITE = find_site('Inserted')
assert SITE is not None


@respx.mock
async def test_search() -> None:
    body = {'scenes': [{'id': 7, 'title': 'Cool Scene', 'slug': 'cool-scene', 'publish_date': '2021-03-04'}]}
    respx.get('https://inserted.com/api/search/cool%20scene').mock(return_value=httpx.Response(200, json=body))
    results: list[SearchResult] = []
    await RadicalCashClient().search(results, search_context(SITE, 'cool scene'))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://inserted.com/videos/cool-scene'
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_detail() -> None:
    url = 'https://inserted.com/videos/cool-scene'
    content = {
        'title': 'Cool Scene',
        'description': 'A summary',
        'site': 'Inserted',
        'publish_date': '2021-03-04',
        'tags': ['Anal', 'Teen'],
        'models_thumbs': [{'name': 'Jane Doe', 'thumb': 'https://cdn/jane.jpg'}],
        'trailer_screencap': 'https://cdn/cap.jpg',
        'previews': {'full': ['https://cdn/p1.jpg']},
    }
    page = f'<html><body><script type="application/json">{json.dumps({"props": {"pageProps": {"content": content}}})}</script></body></html>'
    respx.get(url).mock(return_value=httpx.Response(200, text=page))
    detail = await RadicalCashClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Radical Cash'
    assert detail.tagline == 'Inserted'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Anal', 'Teen']
    assert detail.actors is not None and detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://cdn/jane.jpg'
    assert detail.art == ['https://cdn/cap.jpg', 'https://cdn/p1.jpg']
