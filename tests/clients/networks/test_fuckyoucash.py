from __future__ import annotations

import httpx
import pytest
import respx

from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.networks.fuckyoucash import FuckYouCashClient
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
    respx.get('https://cum4k.com/api/releases/cool-scene').mock(return_value=httpx.Response(200, json=_RELEASE))
    respx.route(method='GET', url__regex=r'cum4k\.com/api/releases/.*').mock(return_value=httpx.Response(404))
    results: list[SearchResult] = []
    await FuckYouCashClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert FuckYouCashClient().decode(results[0].cur_id).startswith('cool-scene|')


@respx.mock
async def test_search_keeps_a_title_that_only_looks_like_a_name() -> None:
    route = respx.get('https://cum4k.com/api/releases/casting-couch-x').mock(return_value=httpx.Response(200, json=_RELEASE))
    results: list[SearchResult] = []
    await FuckYouCashClient().search(results, _ctx(title='Casting Couch X'))
    assert route.call_count == 1
    assert len(results) == 1


@respx.mock
async def test_detail() -> None:
    respx.get('https://cum4k.com/api/releases/cool-scene').mock(return_value=httpx.Response(200, json=_RELEASE))
    detail = await FuckYouCashClient().fetch_scene_detail('cool-scene|2021-03-04', SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Cum4K'
    assert detail.tagline == ''
    assert detail.collections == ['Cum4K']
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Teen', 'Creampie']


@respx.mock
async def test_detail_of_a_grouped_site_uses_the_sub_group_as_studio() -> None:
    grouped = find_site('18 Years Old')
    assert grouped is not None and grouped.sub_group == 'Porn Pros'
    release = {**_RELEASE, 'sponsor': {'name': '18YearsOld'}}
    respx.get('https://pornpros.com/api/releases/cool-scene').mock(return_value=httpx.Response(200, json=release))
    detail = await FuckYouCashClient().fetch_scene_detail('cool-scene|2021-03-04', grouped)
    assert detail is not None
    assert detail.studio == 'Porn Pros'
    assert detail.tagline == '18YearsOld'
    assert detail.collections == ['18YearsOld']


@respx.mock
async def test_detail_drops_a_sub_site_that_repeats_the_studio() -> None:
    grouped = find_site('Porn Pros')
    assert grouped is not None
    release = {**_RELEASE, 'sponsor': {'name': 'Porn Pros'}}
    respx.get('https://pornpros.com/api/releases/cool-scene').mock(return_value=httpx.Response(200, json=release))
    detail = await FuckYouCashClient().fetch_scene_detail('cool-scene|2021-03-04', grouped)
    assert detail is not None
    assert detail.studio == 'Porn Pros'
    assert detail.tagline == ''
    assert detail.collections == ['Porn Pros']
    names = [a.name for a in (detail.actors or [])]
    assert names == ['Jane Doe', 'John Smith']
    assert detail.art == ['https://cdn/p.jpg?token=x', 'https://cdn/t1.jpg?token=y']


@respx.mock
async def test_detail_renames_a_shared_first_name_per_scene() -> None:
    release = {**_RELEASE, 'title': '40oz Zombie Booty', 'actors': [{'name': 'Vanessa'}]}
    respx.get('https://cum4k.com/api/releases/40oz-zombie-booty').mock(return_value=httpx.Response(200, json=release))
    detail = await FuckYouCashClient().fetch_scene_detail('40oz-zombie-booty|2021-03-04', SITE)
    assert detail is not None
    assert [a.name for a in detail.actors] == ['Vanessa Cruz']


@respx.mock
async def test_detail_leaves_an_unlisted_scene_alone() -> None:
    release = {**_RELEASE, 'title': 'Some Other Scene', 'actors': [{'name': 'Vanessa'}]}
    respx.get('https://cum4k.com/api/releases/some-other-scene').mock(return_value=httpx.Response(200, json=release))
    detail = await FuckYouCashClient().fetch_scene_detail('some-other-scene|2021-03-04', SITE)
    assert detail is not None
    assert [a.name for a in detail.actors] == ['Vanessa']


@respx.mock
async def test_detail_rename_can_expand_into_two_credits() -> None:
    release = {**_RELEASE, 'title': 'Juicy Ass Moon Bounce', 'actors': [{'name': 'Zo'}]}
    respx.get('https://cum4k.com/api/releases/juicy-ass-moon-bounce').mock(return_value=httpx.Response(200, json=release))
    detail = await FuckYouCashClient().fetch_scene_detail('juicy-ass-moon-bounce|2021-03-04', SITE)
    assert detail is not None
    assert [a.name for a in detail.actors] == ['Daiquiri Holland', 'Vanessa Monet']


@respx.mock
async def test_data18_receives_pornplus_while_the_studio_stays_porn_plus(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    async def spy(self: object, metadata: object, site: object, *, scene_id: str | None = None, providers: list[str], **kw: object) -> None:
        seen.append(providers)

    monkeypatch.setattr(FuckYouCashClient, 'enrich_from_data18', spy)
    grouped = find_site('Porn+')
    assert grouped is not None and grouped.sub_group == 'Porn+'
    release = {**_RELEASE, 'sponsor': {'name': 'Shower 4K'}}
    respx.get('https://pornplus.com/api/releases/cool-scene').mock(return_value=httpx.Response(200, json=release))

    detail = await FuckYouCashClient().fetch_scene_detail('cool-scene|2021-03-04', grouped)

    assert detail is not None
    assert detail.studio == 'Porn+'
    assert 'PornPlus' in seen[0]
    assert 'Porn+' not in seen[0]
