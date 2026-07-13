from __future__ import annotations

import httpx
import pytest
import respx

import app.clients.networks.pervcity as pc_mod
from app.clients.base import SearchContext, SearchResult
from app.clients.networks.pervcity import PervCityClient
from app.registry import find_site

SITE = find_site('Anal Overdose')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _no_web(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _none(*_a: object, **_k: object) -> list[str]:
        return []

    monkeypatch.setattr(pc_mod, 'web_search_urls', _none)


@respx.mock
async def test_search_native() -> None:
    url = 'https://analoverdose.com/search.php?query=cool+scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text='<div class="videoBlock"><h2><a href="https://analoverdose.com/scene/7">Cool Scene</a></h2><div class="date">March 4, 2021</div></div>',
        )
    )
    results: list[SearchResult] = []
    await PervCityClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://analoverdose.com/scene/7'
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_detail_actor_host_swap() -> None:
    url = 'https://analoverdose.com/scene/7'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1>Cool Scene</h1>
              <div class="infoBox clear"><p>A summary.</p></div>
              <div class="about"><h3>About Anal Overdose</h3></div>
              <div class="tagcats"><a>Anal</a><a>Anal</a></div>
              <h2><span><a href="https://analoverdose.com/model/jane">Jane Doe</a></span></h2>
              <div class="snap"><img src0_3x="https://cdn/s1.jpg?token=x" /></div>
            </body></html>""",
        )
    )
    # legacy host swap: model link analoverdose.com -> pervcity.com
    respx.get('https://pervcity.com/model/jane').mock(return_value=httpx.Response(200, text='<div class="starPic"><img src="https://cdn/jane.jpg" /></div>'))
    detail = await PervCityClient().fetch_scene_detail('https://analoverdose.com/scene/7|2021-03-04', SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'PervCity'
    assert detail.tagline == 'Anal Overdose'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Anal']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://cdn/jane.jpg'
    assert detail.art == ['https://cdn/s1.jpg?token=x']
