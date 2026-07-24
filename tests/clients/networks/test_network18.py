from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.networks.network18 import Network18Client
from phoenixadult.registry import find_site

SITE = find_site('Fit18')
assert SITE is not None
_ENDPOINT = 'https://fit18.team18media.app/graphql'


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search() -> None:
    body = {
        'data': {
            'search': {
                'search': {
                    'result': [
                        {'type': 'VIDEO', 'itemId': 'model1:scene7', 'name': 'Cool Scene', 'images': ['https://cdn/t.jpg']},
                        {'type': 'MODEL', 'itemId': 'modelX', 'name': 'Some Model'},
                    ]
                }
            }
        }
    }
    respx.post(_ENDPOINT).mock(return_value=httpx.Response(200, json=body))
    results: list[SearchResult] = []
    await Network18Client().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert Network18Client().decode(results[0].cur_id) == 'model1:scene7'
    assert results[0].thumb_url == 'https://cdn/t.jpg'


@respx.mock
async def test_detail() -> None:
    find_body = {
        'data': {
            'video': {
                'find': {
                    'result': {
                        'videoId': 'model1:scene7',
                        'title': 'Cool Scene',
                        'galleryCount': 1,
                        'description': {'long': 'A summary'},
                        'talent': [{'type': 'FEMALE', 'talent': {'talentId': 'jane', 'name': 'Jane Doe'}}],
                    }
                }
            }
        }
    }
    actor_assets = {'data': {'asset': {'batch': {'result': [{'serve': {'uri': 'https://cdn/jane.jpg'}}]}}}}
    image_assets = {'data': {'asset': {'batch': {'result': [{'serve': {'uri': 'https://cdn/vt.jpg'}}, {'serve': {'uri': 'https://cdn/g1.jpg'}}]}}}}

    route = respx.post(_ENDPOINT)
    route.side_effect = [
        httpx.Response(200, json=find_body),
        httpx.Response(200, json=actor_assets),
        httpx.Response(200, json=image_assets),
    ]
    detail = await Network18Client().fetch_scene_detail('model1:scene7', SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Fit18'
    assert detail.collections == ['Fit18']
    assert detail.genres == ['Young', 'Gym']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://cdn/jane.jpg'
    assert detail.actors[0].gender == 'female'
    assert detail.art == ['https://cdn/vt.jpg', 'https://cdn/g1.jpg']
