from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.networks.teencoreclub import TeenCoreClubClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site

SITE = find_site('Young Throats')
assert SITE is not None
_API = 'https://api.fundorado.com/api'


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search() -> None:
    body = {'videos': {'last_page': 1, 'data': [{'id': 77, 'title': {'en': 'Cool Scene'}, 'publication_date': '2021-03-04'}]}}
    respx.get(url__startswith=f'{_API}/videos/browse/search/').mock(return_value=httpx.Response(200, json=body))
    results: list[SearchResult] = []
    await TeenCoreClubClient().search(results, _ctx(scene_id='77'))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].score == 100
    assert TeenCoreClubClient().decode(results[0].cur_id) == f'{_API}/videodetail/77'


@respx.mock
async def test_detail() -> None:
    url = f'{_API}/videodetail/77'
    body = {
        'video': {
            'id': 77,
            'title': {'en': 'Cool Scene'},
            'description': {'en': 'A summary.'},
            'publication_date': '2021-03-04',
            'actors': [{'name': 'Jane Doe'}],
            'genres': [{'title': {'en': 'Teen'}}],
            'labels': [{'name': 'YoungThroats.Special'}],
            'artwork': {'small': 'https://cdn/a-sm.jpg', 'large': 'https://cdn/a-lg.jpg'},
            'screenshots': ['https://cdn/s1.jpg'],
        }
    }
    respx.get(url).mock(return_value=httpx.Response(200, json=body))
    detail = await TeenCoreClubClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Teen Core Club'
    assert detail.tagline == 'Young Throats'
    assert detail.collections == ['Young Throats']
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Teen']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.art == ['https://cdn/a-sm.jpg', 'https://cdn/a-lg.jpg', 'https://cdn/s1.jpg']


@respx.mock
async def test_detail_bic_title() -> None:
    url = f'{_API}/videodetail/9'
    body = {'video': {'id': 9, 'title': {'en': 'bic_12345'}, 'actors': [{'name': 'Jane Doe'}, {'name': 'John Smith'}]}}
    respx.get(url).mock(return_value=httpx.Response(200, json=body))
    detail = await TeenCoreClubClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Jane Doe & John Smith'
