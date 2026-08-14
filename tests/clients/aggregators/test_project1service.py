from __future__ import annotations

import httpx
import pytest
import respx

import phoenixadult.clients.aggregators.data18 as data18_module
from phoenixadult.clients.aggregators.project1service import Project1ServiceClient, _service_url
from phoenixadult.clients.base import SceneContext, SearchContext, SearchResult
from phoenixadult.registry import find_site

SITE = find_site('Brazzers')
assert SITE is not None
_API = 'https://site-api.project1service.com'


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


def _token_head() -> None:
    respx.head('http://www.brazzers.com').mock(return_value=httpx.Response(200, headers=[('set-cookie', 'instance_token=tok123; Path=/')]))


def test_service_url() -> None:
    assert _service_url('akamai=hash/path/p.jpg', 'https://img.example.com/') == 'https://img.example.com/path/p.jpg'
    assert _service_url(None, 'https://img.example.com/') is None


_RELEASE = {
    'id': 777,
    'title': 'Cool Scene',
    'description': 'A summary.',
    'brand': 'Brazzers',
    'dateReleased': '2021-03-04 00:00:00',
    'collections': [{'name': 'Pornstars Like It Big'}],
    'tags': [{'name': 'Anal'}],
    'actors': [{'id': 5, 'name': 'Jane Doe'}],
    'images': {'poster': {'0': {'xx': {'url': 'akamai=hash/path/p.jpg'}}}},
}


@respx.mock
async def test_search() -> None:
    _token_head()
    respx.get(url__startswith=f'{_API}/v2/releases').mock(return_value=httpx.Response(200, json={'result': [_RELEASE]}))
    results: list[SearchResult] = []
    await Project1ServiceClient().search(results, _ctx())
    titles = {r.title for r in results}
    assert 'Cool Scene' in titles
    assert '[Trailer] Cool Scene' in titles
    cool = next(r for r in results if r.title == 'Cool Scene')
    assert cool.thumb_url == 'https://image-service-ht.project1content.com/path/p.jpg'
    assert cool.release_date == '2021-03-04'
    assert cool.display_date == '2021-03-04'
    assert cool.subsite == 'Pornstars Like It Big'


@respx.mock
async def test_search_date_falls_back_to_filename_date() -> None:
    _token_head()
    dateless = {**_RELEASE, 'dateReleased': None}
    respx.get(url__startswith=f'{_API}/v2/releases').mock(return_value=httpx.Response(200, json={'result': [dateless]}))
    results: list[SearchResult] = []
    await Project1ServiceClient().search(results, _ctx(search_date='2021-03-04'))
    cool = next(r for r in results if r.title == 'Cool Scene')
    assert cool.release_date == '2021-03-04'
    assert cool.display_date is None


@respx.mock
async def test_detail() -> None:
    _token_head()
    respx.get(url__startswith=f'{_API}/v2/releases').mock(return_value=httpx.Response(200, json={'result': [_RELEASE]}))
    actor = {'id': 5, 'name': 'Jane Doe', 'gender': 'female', 'images': {'profile': {'0': {'xs': {'url': 'x=h/a/jane.jpg'}}}}}
    respx.get(url__startswith=f'{_API}/v1/actors').mock(return_value=httpx.Response(200, json={'result': [actor]}))
    detail = await Project1ServiceClient().fetch_scene_detail('777|scene|2021-03-04', SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Brazzers'
    assert detail.tagline == 'Pornstars Like It Big'
    assert detail.collections == ['Pornstars Like It Big']
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Anal']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].gender == 'female'
    assert detail.actors[0].photo_url == 'https://image-service-ht.project1content.com/a/jane.jpg'
    assert detail.art == ['https://image-service-ht.project1content.com/path/p.jpg']


@respx.mock
async def test_detail_data18_slug_uses_ctx_subsite_when_collections_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('DATA18_ENABLE', 'true')
    _token_head()
    release = {**_RELEASE, 'collections': []}
    respx.get(url__startswith=f'{_API}/v2/releases').mock(return_value=httpx.Response(200, json={'result': [release]}))
    respx.get(url__startswith=f'{_API}/v1/actors').mock(return_value=httpx.Response(200, json={'result': []}))
    captured: dict[str, object] = {}

    class FakeData18(data18_module.Data18Client):
        async def find_scene_url(
            self, scene_id: str | None, query: str, providers: list[str], scene_date: object, kind: str = 'scene', search: bool = True
        ) -> None:
            captured['mapping_id'] = scene_id
            captured['providers'] = providers
            return None

        async def fetch_images(self, url: str) -> list[str]:
            return []

    monkeypatch.setattr(data18_module, 'Data18Client', FakeData18)
    detail = await Project1ServiceClient().fetch_scene_detail('777|scene|2021-03-04', SITE, SceneContext(subsite='Teens Like It Big'))
    assert detail is not None
    assert captured['mapping_id'] == 'cool-scene-teenslikeitbig'
    assert 'Teens Like It Big' in captured['providers']  # type: ignore[operator]


@respx.mock
async def test_search_forces_brazzers_live_subsite() -> None:
    _token_head()
    live = find_site('Brazzers Live')
    assert live is not None
    respx.get(url__startswith=f'{_API}/v2/releases').mock(return_value=httpx.Response(200, json={'result': [_RELEASE]}))
    ctx = SearchContext(title='cool scene', encoded='cool+scene', search_site='Brazzers Live', site_info=SITE)
    results: list[SearchResult] = []
    await Project1ServiceClient().search(results, ctx)
    cool = next(r for r in results if r.title == 'Cool Scene')
    assert cool.subsite == 'Brazzers Live'


@respx.mock
async def test_scene_id_hit_skips_the_text_search() -> None:
    _token_head()
    hit = {**_RELEASE, 'id': 3940141, 'title': "The Coach's Wife", 'collections': [{'name': 'Brazzers'}]}
    id_route = respx.get(url__regex=rf'{_API}/v2/releases\?type=\w+&id=3940141').mock(return_value=httpx.Response(200, json={'result': [hit]}))
    search_route = respx.get(url__regex=rf'{_API}/v2/releases\?type=\w+&search=.*').mock(return_value=httpx.Response(200, json={'result': []}))
    results: list[SearchResult] = []
    await Project1ServiceClient().search(results, _ctx('3940141 the coachs wife'))
    assert id_route.called
    assert not search_route.called
    assert any(r.score == 100 and r.title == "The Coach's Wife" for r in results)


@respx.mock
async def test_scene_id_miss_falls_back_to_the_text_search() -> None:
    _token_head()
    id_route = respx.get(url__regex=rf'{_API}/v2/releases\?type=\w+&id=3940141').mock(return_value=httpx.Response(200, json={'result': []}))
    search_route = respx.get(url__regex=rf'{_API}/v2/releases\?type=\w+&search=.*').mock(return_value=httpx.Response(200, json={'result': [_RELEASE]}))
    results: list[SearchResult] = []
    await Project1ServiceClient().search(results, _ctx('3940141 cool scene'))
    assert id_route.called
    assert search_route.called
    assert any(r.title == 'Cool Scene' for r in results)


@respx.mock
async def test_scene_id_near_miss_still_searches_and_dedupes() -> None:
    _token_head()
    other = {**_RELEASE, 'id': 3940142}
    respx.get(url__regex=rf'{_API}/v2/releases\?type=\w+&id=3940141').mock(return_value=httpx.Response(200, json={'result': [other]}))
    respx.get(url__regex=rf'{_API}/v2/releases\?type=\w+&search=.*').mock(return_value=httpx.Response(200, json={'result': [other]}))
    results: list[SearchResult] = []
    await Project1ServiceClient().search(results, _ctx('3940141 cool scene'))
    assert len(results) == 4
    assert all(r.score < 100 for r in results)
