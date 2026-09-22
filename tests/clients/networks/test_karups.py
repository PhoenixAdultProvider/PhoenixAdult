from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.networks.karups import KarupsClient
from phoenixadult.models.scrape import SearchResult
from phoenixadult.registry import find_site
from tests.support import search_context

SITE = find_site('KarupsHA')
assert SITE is not None


@respx.mock
async def test_search_model_to_videos() -> None:
    respx.get('https://www.karups.com/models/search/jane-doe/').mock(
        return_value=httpx.Response(200, text='<div class="item-inside"><a href="/models/jane-doe"></a></div>')
    )
    model_html = (
        '<div class="listing-videos"><div class="item">'
        '<a href="/video/77"></a><span class="title">Cool Scene</span>'
        '<span class="date">March 4th, 2021</span></div></div>'
    )
    respx.get('https://www.karups.com/models/jane-doe').mock(return_value=httpx.Response(200, text=model_html))
    results: list[SearchResult] = []
    await KarupsClient().search(results, search_context(SITE, 'jane doe', space='%20'))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://www.karups.com/video/77'
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_detail() -> None:
    url = 'https://www.karups.com/video/77'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1><span class="sup-title"><span>KarupsHA</span></span><span class="title">Cool Scene</span></h1>
              <div class="content-information-description"><p>A summary.</p></div>
              <span class="date"><span class="content">KarupsHA Video added on March 4th, 2021</span></span>
              <span class="models"><a href="/models/jane-doe">Jane Doe</a></span>
              <div class="video-player"><video poster="/img/poster.jpg"></video></div>
            </body></html>""",
        )
    )
    respx.get('https://www.karups.com/models/jane-doe').mock(return_value=httpx.Response(200, text='<div class="model-thumb"><img src="/p/jane.jpg" /></div>'))
    detail = await KarupsClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Karups'
    assert detail.tagline == 'KarupsHA'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Amateur']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://www.karups.com/p/jane.jpg'
    assert detail.art == ['https://www.karups.com/img/poster.jpg']
