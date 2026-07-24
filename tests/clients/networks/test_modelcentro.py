from __future__ import annotations

import json

import httpx
import respx

from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.networks.modelcentro import ModelCentroClient
from phoenixadult.registry import find_site

SITE = find_site('Romi Rain')
JOWM = find_site('Jerk Off with Me')
assert SITE is not None and JOWM is not None

_TOKEN_HTML = '<html><script>var x = {"ah":"ZYX","aet":99};</script></html>'


def _ctx(site, title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=site.name, site_info=site, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search() -> None:
    respx.get('https://www.romirain.com/videos/').mock(return_value=httpx.Response(200, text=_TOKEN_HTML))
    list_body = {
        'response': {
            'collection': {
                '5': {
                    'id': 5,
                    'title': 'Cool Scene',
                    'sites': {'collection': {'5': {'publishDate': '2021-03-04 00:00:00'}}},
                    '_resources': {'base': [{'url': 'https://cdn/a.jpg'}]},
                }
            }
        }
    }
    respx.get(url__startswith='https://www.romirain.com/sapi/XYZ/99/content.load').mock(return_value=httpx.Response(200, json=list_body))
    results: list[SearchResult] = []
    await ModelCentroClient().search(results, _ctx(SITE, '5 cool scene', scene_id='5'))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://www.romirain.com/scene/5/'
    assert results[0].display_date == '2021-03-04'
    assert results[0].score == 100


@respx.mock
async def test_detail() -> None:
    respx.get(url__startswith='https://www.romirain.com/scene/5/').mock(return_value=httpx.Response(200, text=_TOKEN_HTML))
    detail_body = {
        'response': {
            'collection': [
                {
                    'id': 5,
                    'title': 'Cool Scene',
                    'description': 'A summary.',
                    'sites': {'collection': {'5': {'publishDate': '2021-03-04 00:00:00'}}},
                    'tags': {'collection': [{'alias': 'hardcore'}, {'alias': 'big-tits'}]},
                }
            ]
        }
    }
    model_body = {'response': {'collection': [{'modelId': {'collection': [{'stageName': 'Jane Doe'}]}}]}}
    respx.get(url__startswith='https://www.romirain.com/sapi/XYZ/99/content.load').mock(return_value=httpx.Response(200, json=detail_body))
    respx.get(url__startswith='https://www.romirain.com/sapi/XYZ/99/model.getModelContent').mock(return_value=httpx.Response(200, json=model_body))

    payload = json.dumps({'id': 5, 'title': 'Cool Scene', 'releaseDate': '2021-03-04', 'art': ['https://cdn/a.jpg']})
    detail = await ModelCentroClient().fetch_scene_detail(payload, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Romi Rain'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['hardcore', 'big-tits']
    names = [a.name for a in detail.actors]
    assert 'Jane Doe' in names and 'Romi Rain' in names
    assert detail.art == ['https://cdn/a.jpg']


@respx.mock
async def test_jerkoffwithme_tags_as_actors() -> None:
    respx.get(url__startswith='https://www.jerkoffwithme.com/scene/5/').mock(return_value=httpx.Response(200, text=_TOKEN_HTML))
    detail_body = {'response': {'collection': [{'id': 5, 'title': 'Cool', 'tags': {'collection': [{'alias': 'jane-doe'}]}}]}}
    respx.get(url__startswith='https://www.jerkoffwithme.com/sapi/XYZ/99/content.load').mock(return_value=httpx.Response(200, json=detail_body))
    respx.get(url__startswith='https://www.jerkoffwithme.com/sapi/XYZ/99/model.getModelContent').mock(
        return_value=httpx.Response(200, json={'response': {'collection': []}})
    )
    payload = json.dumps({'id': 5, 'title': 'Cool', 'releaseDate': '', 'art': []})
    detail = await ModelCentroClient().fetch_scene_detail(payload, JOWM)
    assert detail is not None
    assert detail.genres == []
    assert [a.name for a in detail.actors] == ['jane doe']
