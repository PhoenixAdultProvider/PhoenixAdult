from __future__ import annotations

import httpx
import pytest
import respx

import phoenixadult.clients.networks.newsensations as ns_mod
from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.networks.newsensations import NewSensationsClient
from phoenixadult.registry import find_site

SITE = find_site('New Sensations')
assert SITE is not None


@pytest.fixture(autouse=True)
def _strip_actors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('SEARCH_STRIP_ACTORS', SITE.name)


def _ctx(title: str = 'Jane Doe Cool Scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search_url_guess(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ns_mod, 'web_search_available', lambda: False)
    hit = 'http://www.newsensations.com/tour_ns/updates/Cool-Scene.html'
    respx.get(hit).mock(return_value=httpx.Response(200, text='<div class="indScene"><h1>Cool Scene</h1></div>'))
    respx.get(url__startswith='http://www.newsensations.com/tour_ns/').mock(return_value=httpx.Response(404, text=''))
    results: list[SearchResult] = []
    await NewSensationsClient().search(results, _ctx())
    assert any(r.title == 'Cool Scene' and r.scene_url == hit for r in results)


@respx.mock
async def test_detail_scene() -> None:
    url = 'http://www.newsensations.com/tour_ns/updates/cool.html'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <div class="indScene"><h1>Cool Scene</h1></div>
              <div class="description"><h2>Description: A summary.</h2></div>
              <div class="sceneDateP"><span>March 4, 2021</span></div>
              <div class="sceneTextLink"><span class="tour_update_models"><a href="/models/jane.html">Jane Doe</a></span></div>
              <span id="trailer_thumb"><img src="/img/t.jpg" /></span>
            </body></html>""",
        )
    )
    respx.get('http://www.newsensations.com/models/jane.html').mock(
        return_value=httpx.Response(200, text='<div class="modelBioPic"><img src0_3x="/p/jane.jpg" /></div>')
    )
    detail = await NewSensationsClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'New Sensations'
    assert detail.tagline == ''
    assert detail.collections == ['New Sensations']
    assert detail.release_date == '2021-03-04'
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'http://www.newsensations.com/p/jane.jpg'
    assert detail.art == ['http://www.newsensations.com/img/t.jpg']


@respx.mock
async def test_detail_dvd() -> None:
    url = 'http://www.newsensations.com/tour_ns/dvds/cool.html'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <div class="indSceneDVD"><h1>Cool DVD</h1></div>
              <div class="description"><h2>Description: A DVD summary.</h2></div>
              <div class="datePhotos">RELEASED: 2021-03-04</div>
              <div class="textLink"><a>Anal</a></div>
              <span class="tour_update_models"><a href="/models/jane.html">Jane Doe</a></span>
              <span id="trailer_thumb"><img src="/img/t.jpg" /></span>
              <div class="videoBlock"><img src0_3x="/img/v1.jpg" /></div>
            </body></html>""",
        )
    )
    respx.get('http://www.newsensations.com/models/jane.html').mock(
        return_value=httpx.Response(200, text='<div class="modelBioPic"><img src0_3x="/p/jane.jpg" /></div>')
    )
    detail = await NewSensationsClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool DVD'
    assert detail.tagline == 'Cool DVD'
    assert detail.collections == ['Cool DVD']
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Anal']
    assert detail.art == ['http://www.newsensations.com/img/t.jpg', 'http://www.newsensations.com/img/v1.jpg']
