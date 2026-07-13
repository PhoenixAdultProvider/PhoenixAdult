from __future__ import annotations

import json

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.networks.steppedup import SteppedUpClient
from app.registry import find_site

SITE = find_site('True Anal')
assert SITE is not None
_BID = 'abc123'


def _probe(build_id: str) -> str:
    return f'<html><body><script type="application/json">{json.dumps({"buildId": build_id})}</script></body></html>'


def _ctx(title: str = 'Jane Doe', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search() -> None:
    respx.get('https://tour.trueanal.com/models/jane-doe').mock(return_value=httpx.Response(200, text=_probe(_BID)))
    body = {'pageProps': {'model_contents': [{'title': 'Cool Scene', 'slug': 'cool-scene', 'publish_date': '2021-03-04'}]}}
    respx.get(f'https://tour.trueanal.com/_next/data/{_BID}/models/jane-doe.json').mock(return_value=httpx.Response(200, json=body))
    results: list[SearchResult] = []
    await SteppedUpClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert SteppedUpClient().decode(results[0].cur_id).startswith('cool-scene|')


@respx.mock
async def test_detail() -> None:
    respx.get('https://tour.trueanal.com/scenes/cool-scene').mock(return_value=httpx.Response(200, text=_probe(_BID)))
    content = {
        'title': 'Cool Scene',
        'description': 'A summary.',
        'site': 'True Anal',
        'publish_date': '2021-03-04',
        'tags': ['Anal'],
        'models_thumbs': [{'name': 'Jane Doe', 'thumb': 'https://cdn/jane.jpg'}],
        'trailer_screencap': 'https://cdn/cap.jpg',
        'thumbs': ['https://cdn/t1.jpg'],
    }
    respx.get(f'https://tour.trueanal.com/_next/data/{_BID}/scenes/cool-scene.json').mock(
        return_value=httpx.Response(200, json={'pageProps': {'content': content}})
    )
    detail = await SteppedUpClient().fetch_scene_detail('cool-scene|2021-03-04', SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.studio == 'Stepped Up Media'
    assert detail.tagline == 'True Anal'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Anal']
    assert detail.actors is not None and detail.actors[0].photo_url == 'https://cdn/jane.jpg'
    assert detail.art == ['https://cdn/cap.jpg', 'https://cdn/t1.jpg']
