from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.networks.pornpros import PornProsClient
from phoenixadult.registry import find_site

SITE = find_site('Cum4K')
assert SITE is not None


_RELEASE = {
    'title': 'Cool Scene',
    'description': 'A summary.',
    'sponsor': {'name': 'Cum4K'},
    'releasedAt': '2021-03-04',
    'tags': ['Teen'],
    'actors': [{'name': 'Jane Doe & John Smith'}],
    'posterUrl': 'https://cdn/p.jpg?token=x',
    'thumbUrls': ['https://cdn/t1.jpg?token=y'],
}


def _ctx(title: str = 'Jane Doe Cool Scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search_falls_back_past_the_actor_prefix() -> None:
    respx.get('https://cum4k.com/api/releases/jane-doe-cool-scene').mock(return_value=httpx.Response(404))
    respx.get('https://cum4k.com/api/releases/jane-doe-cool--scene').mock(return_value=httpx.Response(404))
    respx.get('https://cum4k.com/api/releases/cool-scene').mock(return_value=httpx.Response(200, json=_RELEASE))
    results: list[SearchResult] = []
    await PornProsClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert PornProsClient().decode(results[0].cur_id).startswith('cool-scene|')


@respx.mock
async def test_search_keeps_a_title_that_only_looks_like_a_name() -> None:
    route = respx.get('https://cum4k.com/api/releases/casting-couch-x').mock(return_value=httpx.Response(200, json=_RELEASE))
    results: list[SearchResult] = []
    await PornProsClient().search(results, _ctx(title='Casting Couch X'))
    assert route.call_count == 1
    assert len(results) == 1


@respx.mock
async def test_detail() -> None:
    respx.get('https://cum4k.com/api/releases/cool-scene').mock(return_value=httpx.Response(200, json=_RELEASE))
    detail = await PornProsClient().fetch_scene_detail('cool-scene|2021-03-04', SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Porn Pros'
    assert detail.tagline == 'Cum4K'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Teen', 'Creampie']
    names = [a.name for a in (detail.actors or [])]
    assert names == ['Jane Doe', 'John Smith']
    assert detail.art == ['https://cdn/p.jpg?token=x', 'https://cdn/t1.jpg?token=y']
