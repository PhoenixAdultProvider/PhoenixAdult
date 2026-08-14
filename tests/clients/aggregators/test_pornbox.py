from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.aggregators.pornbox import PornboxClient
from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.registry import find_site

SITE = find_site('Pornbox')
assert SITE is not None


@respx.mock
async def test_search_lifts_match_id() -> None:
    respx.get('https://www.pornbox.com/store/search?q=Jane').mock(
        return_value=httpx.Response(200, json={'content': {'contents': [{'scene_name': 'Jane Scene abc1', 'content_id': 99, 'publish_date': '2024-01-05'}]}})
    )
    results: list[SearchResult] = []
    await PornboxClient().search(results, SearchContext(title='Jane', encoded='Jane', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == '[abc1] Jane Scene'
    assert results[0].scene_url == 'https://www.pornbox.com/contents/99'


@respx.mock
async def test_search_direct_scene_id() -> None:
    respx.get('https://www.pornbox.com/contents/42001').mock(
        return_value=httpx.Response(200, json={'scene_name': 'Direct Scene', 'publish_date': '2024-03-01'})
    )
    respx.get('https://www.pornbox.com/store/search?q=').mock(return_value=httpx.Response(200, json={'content': {'contents': []}}))
    results: list[SearchResult] = []
    await PornboxClient().search(results, SearchContext(title='', encoded='', search_site=SITE.name, site_info=SITE, scene_id='42001', full_title='42001'))
    direct = next((r for r in results if r.score == 100), None)
    assert direct is not None
    assert direct.title == 'Direct Scene'
    assert direct.scene_url == 'https://www.pornbox.com/contents/42001'


@respx.mock
async def test_detail() -> None:
    url = 'https://www.pornbox.com/contents/99'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            json={
                'scene_name': 'Jane Scene',
                'small_description': '<p>A summary.</p>',
                'studio': 'Some Studio',
                'publish_date': '2024-01-05',
                'niches': [{'niche': 'Anal'}],
                'models': [{'model_name': 'Jane Doe', 'model_id': 7}],
                'player_poster': 'https://cdn/poster.jpg',
                'screenshots': [{'xga_size': 'https://cdn/0.jpg'}, {'xga_size': 'https://cdn/1.jpg'}],
            },
        )
    )
    respx.get('https://www.pornbox.com/model/info/7').mock(return_value=httpx.Response(200, json={'headshot': 'https://cdn/jane.jpg'}))
    detail = await PornboxClient().fetch_scene_detail(f'{url}|2024-01-05', SITE)
    assert detail is not None
    assert detail.title == 'Jane Scene'
    assert detail.studio == 'Pornbox'
    assert detail.tagline == 'Some Studio'
    assert detail.summary == 'A summary.'
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['Anal']
    assert [(a.name, a.photo_url) for a in detail.actors] == [('Jane Doe', 'https://cdn/jane.jpg')]
    assert 'https://cdn/poster.jpg' in detail.art
