from __future__ import annotations

import json

import httpx
import respx

from app.clients.base import SearchContext
from app.clients.networks.bellesa import BellesaClient
from app.registry import find_site

SITE = find_site('Bellesa Films')
assert SITE is not None
_API = 'https://bellesaplus.co/api/rest/v1'


def _body(payload: object) -> str:
    # The API is fronted by Cloudflare; the JSON arrives inside an HTML <body>.
    return f'<html><body>{json.dumps(payload)}</body></html>'


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search() -> None:
    body = {'videos': [{'id': 4321, 'title': 'Cool Scene', 'posted_on': 1614816000}]}
    respx.get(url__startswith=f'{_API}/search').mock(return_value=httpx.Response(200, text=_body(body)))
    results = await BellesaClient().search(_ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].display_date == '2021-03-04'
    assert BellesaClient().decode(results[0].cur_id) == '4321|2021-03-04'


@respx.mock
async def test_search_by_id() -> None:
    video = {'id': 4321, 'title': 'Cool Scene', 'posted_on': 1614816000}
    respx.get(url__startswith=f'{_API}/videos').mock(return_value=httpx.Response(200, text=_body([video])))
    results = await BellesaClient().search(_ctx(scene_id='4321'))
    assert len(results) == 1
    assert results[0].score == 100


@respx.mock
async def test_detail() -> None:
    video = {
        'id': 4321,
        'title': 'Cool Scene',
        'description': 'A summary.',
        'content_provider': [{'name': 'Bellesa House'}],
        'posted_on': 1614816000,
        'tags': 'Anal, Teen',
        'performers': [{'name': 'Jane Doe', 'image': 'https://cdn/jane.jpg'}],
        'image': 'https://cdn/p.jpg',
    }
    respx.get(url__startswith=f'{_API}/videos').mock(return_value=httpx.Response(200, text=_body([video])))
    detail = await BellesaClient().fetch_scene_detail('4321|2021-03-04', SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Bellesa'
    assert detail.tagline == 'Bellesa House'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Anal', 'Teen']
    assert detail.actors is not None and detail.actors[0].name == 'Jane Doe'
    assert detail.raw_image_urls == ['https://cdn/p.jpg']
