from __future__ import annotations

import httpx
import pytest
import respx

import app.clients.networks.radicalcashother as rc_mod
from app.clients.base import SearchContext, SearchResult
from app.clients.networks.radicalcashother import RadicalCashOtherClient
from app.registry import find_site

SITE = find_site('PurgatoryX')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _no_web(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _none(*_a: object, **_k: object) -> list[str]:
        return []

    monkeypatch.setattr(rc_mod, 'web_search_urls', _none)


@respx.mock
async def test_search_purgatoryx() -> None:
    url = 'https://tour.purgatoryx.com/search/cool scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text='<div class="content-item"><h3><a href="/view/7">Cool Scene</a></h3><span class="pub-date">Mar 4, 2021</span></div>',
        )
    )
    results: list[SearchResult] = []
    await RadicalCashOtherClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://purgatoryx.com/view/7'
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_detail_purgatoryx() -> None:
    url = 'https://purgatoryx.com/view/7'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><head><meta name="keywords" content="Anal, Teen, Anal" /></head><body>
              <h1>Cool Scene</h1>
              <div class="description"><p>A summary.</p></div>
              <span class="date">Thursday March 4, 2021</span>
              <div class="model-wrap"><li><h5>Jane Doe</h5><img src="https://cdn/jane.jpg" /></li></div>
            </body></html>""",
        )
    )
    detail = await RadicalCashOtherClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Radical Cash'
    assert detail.tagline == 'PurgatoryX'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Anal', 'Teen']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://cdn/jane.jpg'


@respx.mock
async def test_detail_toughlovex_director() -> None:
    site = find_site('ToughLoveX')
    assert site is not None
    url = 'https://toughlovex.com/view/9'
    respx.get(url).mock(return_value=httpx.Response(200, text='<html><body><h1>X</h1></body></html>'))
    detail = await RadicalCashOtherClient().fetch_scene_detail(f'{url}|2021-03-04', site)
    assert detail is not None
    assert detail.studio == 'Radical Cash'
    assert detail.directors is not None and detail.directors[0].name == 'Charles Dera'
    assert detail.release_date == '2021-03-04'
