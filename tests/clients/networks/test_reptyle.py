from __future__ import annotations

import json

import httpx
import respx

from app.clients.base import SearchContext
from app.clients.networks.reptyle import ReptyleClient
from app.registry import find_site

SITE = find_site('TeamSkeet')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


def _state_html(content: dict) -> str:
    return f'<html><script>window.__INITIAL_STATE__ = {json.dumps({"content": content})};</script></html>'


_SCENE = {
    'title': 'Cool Scene',
    'description': '<p>A summary</p>',
    'img': 'https://cdn/p.jpg',
    'site': {'name': 'Family Strokes'},
    'publishedDate': '2021-03-04T00:00:00Z',
    'models': [{'modelId': 'm1', 'modelName': 'Jane Doe'}, {'modelId': 'm2', 'modelName': 'John Smith'}],
    'tags': ['Taboo'],
    'id': 777,
}


@respx.mock
async def test_search() -> None:
    url = 'https://www.teamskeet.com/movies/cool-scene'
    respx.get(url).mock(return_value=httpx.Response(200, text=_state_html({'moviesContent': {'777': _SCENE}})))
    results = await ReptyleClient().search(_ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].thumb_url == 'https://cdn/p.jpg'
    assert ReptyleClient().decode(results[0].cur_id) == f'777|moviesContent|{url}'


@respx.mock
async def test_detail() -> None:
    url = 'https://www.teamskeet.com/movies/cool-scene'
    respx.get(url).mock(return_value=httpx.Response(200, text=_state_html({'moviesContent': {'777': _SCENE}})))
    respx.get('https://www.teamskeet.com/models/m1').mock(
        return_value=httpx.Response(200, text=_state_html({'modelsContent': {'m1': {'img': 'https://cdn/jane.jpg', 'gender': 'female'}}}))
    )
    respx.get('https://www.teamskeet.com/models/m2').mock(
        return_value=httpx.Response(200, text=_state_html({'modelsContent': {'m2': {'img': 'https://cdn/john.jpg', 'gender': 'male'}}}))
    )
    detail = await ReptyleClient().fetch_scene_detail(f'777|moviesContent|{url}', SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'  # tags stripped, period added
    assert detail.studio == 'TeamSkeet'
    assert detail.tagline == 'Family Strokes'  # sub-site distinct
    assert detail.collections == ['Family Strokes']
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Taboo', 'Threesome']  # >1 actor & not Mylfed
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://cdn/jane.jpg'
    assert detail.actors[0].gender == 'female'
    assert detail.raw_image_urls == ['https://cdn/p.jpg']
