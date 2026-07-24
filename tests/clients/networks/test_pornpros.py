from __future__ import annotations

import httpx
import pytest
import respx

from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.networks.pornpros import PornProsClient
from phoenixadult.registry import find_site

SITE = find_site('Cum4K')
assert SITE is not None


@pytest.fixture(autouse=True)
def _strip_actors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('SEARCH_STRIP_ACTORS', SITE.name)


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
async def test_search() -> None:
    respx.get('https://cum4k.com/api/releases/cool-scene').mock(return_value=httpx.Response(200, json=_RELEASE))
    results: list[SearchResult] = []
    await PornProsClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert PornProsClient().decode(results[0].cur_id).startswith('cool-scene|')


@respx.mock
async def test_detail() -> None:
    respx.get('https://cum4k.com/api/releases/cool-scene').mock(return_value=httpx.Response(200, json=_RELEASE))
    detail = await PornProsClient().fetch_scene_detail('cool-scene|2021-03-04', SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'PornPros'
    assert detail.tagline == 'Cum4K'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Teen', 'Creampie']
    names = [a.name for a in (detail.actors or [])]
    assert names == ['Jane Doe', 'John Smith']
    assert detail.art == ['https://cdn/p.jpg?token=x', 'https://cdn/t1.jpg?token=y']
