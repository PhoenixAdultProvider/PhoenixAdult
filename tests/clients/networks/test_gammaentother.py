from __future__ import annotations

import json

import httpx
import respx

import phoenixadult.clients.networks.gammaentother as geo_mod
from phoenixadult.clients.networks.gammaentother import GammaEntOtherClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site

SITE = find_site('Girlsway')
assert SITE is not None

_SCENE_HIT = {
    'clip_id': 123,
    'movie_id': None,
    'title': 'Cool Scene',
    'url_title': 'cool-scene',
    'release_date': '2021-03-04',
    'description': 'A summary.<br>More.',
    'network_name': 'Girlsway',
    'serie_name': "Mommy's Girl",
    'mainChannel': {'name': "Mommy's Girl"},
    'categories': [{'name': 'Lesbian'}],
    'actors': [{'name': 'Jane Doe', 'actor_id': '9', 'gender': 'female'}],
    'channels': [],
    'pictures': {'nsfw': {'top': {'0': True}}, '0': '/p/cover.jpg'},
}
_ACTOR_HIT = {'pictures': {'1x': '/a/jane.jpg'}}


def _algolia(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    index = body['requests'][0]['indexName']
    if index == 'all_scenes':
        hits = [_SCENE_HIT]
    elif index == 'all_actors':
        hits = [_ACTOR_HIT]
    else:
        hits = []
    return httpx.Response(200, json={'results': [{'hits': hits}]})


def _mock_common() -> None:
    geo_mod._API_KEYS.clear()
    respx.get('https://www.girlsway.com/en/login').mock(return_value=httpx.Response(200, text='var x = {"apiKey":"KEY"};'))
    respx.route(method='POST', url__regex=r'https://tsmkfa364q-dsn\.algolia\.net/.*').mock(side_effect=_algolia)


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '%20'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search() -> None:
    _mock_common()
    results: list[SearchResult] = []
    await GammaEntOtherClient().search(results, _ctx())
    assert any(r.title == 'Cool Scene' for r in results)
    assert next(r for r in results if r.title == 'Cool Scene').subsite == "Mommy's Girl"
    r = next(r for r in results if r.title == 'Cool Scene')
    assert GammaEntOtherClient().decode(r.cur_id) == '123|scenes|2021-03-04'


@respx.mock
async def test_detail() -> None:
    _mock_common()
    detail = await GammaEntOtherClient().fetch_scene_detail('123|scenes|2021-03-04', SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.\nMore.'
    assert detail.studio == 'Girlsway'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Lesbian']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].gender == 'female'
    assert detail.actors[0].photo_url == 'https://images-fame.gammacdn.com/actors/a/jane.jpg'
    assert detail.art[0] == 'https://images-fame.gammacdn.com/movies//p/cover.jpg'
