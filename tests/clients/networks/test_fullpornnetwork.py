from __future__ import annotations

import httpx
import pytest
import respx

import app.clients.networks.fullpornnetwork as fpn_mod
from app.clients.base import SearchContext, SearchResult
from app.registry import find_site

SITE = find_site('James Deen')
assert SITE is not None


def _ctx(title: str = 'jane doe', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '%20'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search_model_crawl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fpn_mod, 'web_search_available', lambda: False)
    url = 'https://jamesdeen.com/models/janedoe.html'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<div class="latest-updates"><div data-setid="1">
              <a class="updateimg" href="/trailers/cool.html"></a> Title: Cool Scene
            </div></div>""",
        )
    )
    results: list[SearchResult] = []
    await fpn_mod.FullPornNetworkClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://jamesdeen.com/trailers/cool.html'


@respx.mock
async def test_detail() -> None:
    url = 'https://jamesdeen.com/trailers/cool.html'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1 class="title_bar">Episode: Cool Scene</h1>
              <div class="video-description"><p class="description-text">A summary.</p></div>
              <div class="video-info"><p>2021-03-04</p>
                <a href="/categories/anal">Anal</a>
                <a href="/models/jane">Jane Doe</a>
              </div>
              <video poster="/img/scene-1x.jpg"></video>
            </body></html>""",
        )
    )
    respx.get('https://jamesdeen.com/models/jane').mock(return_value=httpx.Response(200, text='<img alt="model" src0_3x="/p/jane.jpg" />'))
    detail = await fpn_mod.FullPornNetworkClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Full Porn Network'
    assert detail.tagline == 'James Deen'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Anal']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://jamesdeen.com/p/jane.jpg'
    assert detail.art == ['https://jamesdeen.com/img/scene-3x.jpg']
