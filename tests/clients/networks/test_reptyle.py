from __future__ import annotations

import json

import httpx
import pytest
import respx

import phoenixadult.clients.aggregators.data18 as data18_module
from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.networks.reptyle import ReptyleClient
from phoenixadult.registry import find_site

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
    'id': 'cool-scene',
}


@respx.mock
async def test_search() -> None:
    url = 'https://www.teamskeet.com/movies/cool-scene'
    respx.get(url).mock(return_value=httpx.Response(200, text=_state_html({'moviesContent': {'cool-scene': _SCENE}})))
    results: list[SearchResult] = []
    await ReptyleClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].thumb_url == 'https://cdn/p.jpg'
    assert results[0].subsite == 'Family Strokes'
    assert ReptyleClient().decode(results[0].cur_id) == f'cool-scene|moviesContent|{url}'


@respx.mock
async def test_detail() -> None:
    url = 'https://www.teamskeet.com/movies/cool-scene'
    respx.get(url).mock(return_value=httpx.Response(200, text=_state_html({'moviesContent': {'cool-scene': _SCENE}})))
    respx.get('https://www.teamskeet.com/models/m1').mock(
        return_value=httpx.Response(200, text=_state_html({'modelsContent': {'m1': {'img': 'https://cdn/jane.jpg', 'gender': 'female'}}}))
    )
    respx.get('https://www.teamskeet.com/models/m2').mock(
        return_value=httpx.Response(200, text=_state_html({'modelsContent': {'m2': {'img': 'https://cdn/john.jpg', 'gender': 'male'}}}))
    )
    detail = await ReptyleClient().fetch_scene_detail(f'cool-scene|moviesContent|{url}', SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'TeamSkeet'
    assert detail.tagline == 'Family Strokes'
    assert detail.collections == ['Family Strokes']
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Taboo', 'Threesome']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://cdn/jane.jpg'
    assert detail.actors[0].gender == 'female'
    assert detail.art == ['https://cdn/p.jpg']


@respx.mock
async def test_detail_data18_enrichment_keys_off_the_slug_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('DATA18_ENABLE', 'true')
    url = 'https://www.teamskeet.com/movies/cool-scene'
    respx.get(url).mock(return_value=httpx.Response(200, text=_state_html({'moviesContent': {'cool-scene': _SCENE}})))
    respx.get('https://www.teamskeet.com/models/m1').mock(
        return_value=httpx.Response(200, text=_state_html({'modelsContent': {'m1': {'img': 'https://cdn/jane.jpg', 'gender': 'female'}}}))
    )
    respx.get('https://www.teamskeet.com/models/m2').mock(
        return_value=httpx.Response(200, text=_state_html({'modelsContent': {'m2': {'img': 'https://cdn/john.jpg', 'gender': 'male'}}}))
    )
    captured: dict[str, object] = {}

    class FakeData18(data18_module.Data18Client):
        async def find_scene_url(self, scene_id: str | None, query: str, providers: list[str], scene_date: object, kind: str = 'scene') -> str:
            captured['mapping_id'] = scene_id
            return 'https://www.data18.com/scenes/999'

        async def fetch_images(self, scene_url: str) -> list[str]:
            return ['https://cdn.data18.com/extra.jpg']

    monkeypatch.setattr(data18_module, 'Data18Client', FakeData18)
    detail = await ReptyleClient().fetch_scene_detail(f'cool-scene|moviesContent|{url}', SITE)
    assert detail is not None
    assert captured['mapping_id'] == 'cool-scene-familystrokes'
    assert 'https://cdn.data18.com/extra.jpg' in detail.art


@respx.mock
async def test_a_leading_episode_tag_is_dropped_from_search_and_detail() -> None:
    url = 'https://www.teamskeet.com/movies/cool-scene'
    tagged = {**_SCENE, 'title': 'S1E3: Sneaky, Bratty Lil Stepsis', 'models': []}
    respx.get(url).mock(return_value=httpx.Response(200, text=_state_html({'moviesContent': {'cool-scene': tagged}})))

    results: list[SearchResult] = []
    await ReptyleClient().search(results, _ctx())
    assert [r.title for r in results] == ['Sneaky, Bratty Lil Stepsis']

    detail = await ReptyleClient().fetch_scene_detail(f'cool-scene|moviesContent|{url}', SITE)
    assert detail is not None
    assert detail.title == 'Sneaky, Bratty Lil Stepsis'


@respx.mock
async def test_data18_slug_keeps_the_site_when_it_is_also_the_sub_site(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('DATA18_ENABLE', 'true')
    site = find_site('Family Strokes')
    assert site is not None

    url = 'https://www.familystrokes.com/movies/cool-scene'
    respx.get(url).mock(return_value=httpx.Response(200, text=_state_html({'moviesContent': {'cool-scene': _SCENE}})))
    respx.get(url__regex=r'.*/models/.*').mock(return_value=httpx.Response(200, text=_state_html({'modelsContent': {}})))
    captured: dict[str, object] = {}

    class FakeData18(data18_module.Data18Client):
        async def find_scene_url(self, scene_id: str | None, query: str, providers: list[str], scene_date: object, kind: str = 'scene') -> str | None:
            captured['mapping_id'] = scene_id
            return None

    monkeypatch.setattr(data18_module, 'Data18Client', FakeData18)
    detail = await ReptyleClient().fetch_scene_detail(f'cool-scene|moviesContent|{url}', site)

    assert detail is not None
    assert captured['mapping_id'] == 'cool-scene-familystrokes'


@respx.mock
async def test_search_canonicalizes_an_alias_slug() -> None:
    alias = 'chloe-rose-cool-scene'
    aliased = dict(_SCENE, id='cool-scene')
    respx.get(f'https://www.teamskeet.com/movies/{alias}').mock(return_value=httpx.Response(200, text=_state_html({'videosContent': {alias: aliased}})))

    results: list[SearchResult] = []
    await ReptyleClient().search(results, _ctx('Chloe Rose Cool Scene'))

    assert len(results) == 1
    composite = ReptyleClient().decode(results[0].cur_id)
    assert composite == 'cool-scene|videosContent|https://www.teamskeet.com/movies/cool-scene'
    assert results[0].scene_url == 'https://www.teamskeet.com/movies/cool-scene'
