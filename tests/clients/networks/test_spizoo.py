from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.networks.spizoo import SpizooClient
from phoenixadult.models.scrape import SearchResult
from phoenixadult.registry import find_site
from tests.support import search_context

SITE = find_site('Spizoo')
assert SITE is not None


@respx.mock
async def test_search() -> None:
    url = 'https://www.spizoo.com/search.php?query=%22cool%20scene%22'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text='<div class="model-update row"><a href="/v/7"></a><h3>Cool Scene 4K</h3><div><h4>date</h4>March 4, 2021</div></div>',
        )
    )
    results: list[SearchResult] = []
    await SpizooClient().search(results, search_context(SITE, 'cool scene'))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://www.spizoo.com/v/7'
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_detail() -> None:
    url = 'https://www.spizoo.com/v/7'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1>Cool Scene</h1>
              <i id="site" value="First Class POV"></i>
              <p class="description">A summary.</p>
              <p class="date">2021-03-04 10:00:00</p>
              <div class="categories-holder"><a>Anal, Teen</a></div>
              <div><h3>Pornstars:</h3><a href="/model/jane">Jane.Doe</a></div>
              <section id="scene"><video id="the-video" poster="https://cdn/p.jpg"></video></section>
            </body></html>""",
        )
    )
    respx.get('https://www.spizoo.com/model/jane').mock(
        return_value=httpx.Response(200, text='<div class="model-bio-pic"><img src="https://cdn/jane.jpg" /></div>')
    )
    detail = await SpizooClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Spizoo'
    assert detail.tagline == 'First Class POV'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['anal', 'teen']
    assert detail.actors[0].name == 'JaneDoe'
    assert detail.actors[0].photo_url == 'https://cdn/jane.jpg'
    assert detail.art == ['https://cdn/p.jpg']
