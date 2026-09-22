from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.networks.perfectgonzo import PerfectGonzoClient
from phoenixadult.models.scrape import SearchResult
from phoenixadult.registry import find_site
from tests.support import search_context

SITE = find_site('All Internal')
assert SITE is not None


@respx.mock
async def test_search() -> None:
    url = 'https://www.perfectgonzo.com/movies?tag=allinternal&q=cool+scene'
    respx.get(url).mock(
        return_value=httpx.Response(200, text='<div class="itemm"><a href="/movie/7" title="Cool Scene"></a><span class="nm-date">March 4, 2021</span></div>')
    )
    results: list[SearchResult] = []
    await PerfectGonzoClient().search(results, search_context(SITE, 'cool scene'))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://www.perfectgonzo.com/movie/7'
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_detail() -> None:
    url = 'https://www.perfectgonzo.com/movie/7'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h2>Cool Scene</h2>
              <div class="col-sm-8 col-md-8 no-padding-side"><p>A summary.</p></div>
              <div class="col-sm-6 col-md-6 no-padding-left no-padding-right text-right"><span>Added March 4, 2021</span></div>
              <div class="col-sm-8 col-md-8 no-padding-side tag-container"><a>Anal</a><a>Anal</a></div>
              <div class="col-sm-3 col-md-3 col-md-offset-1 no-padding-side"><p><a href="/model/jane">Jane Doe</a></p></div>
              <video poster="/img/p.jpg"></video>
              <ul class="bxslider_screenshots"><img data-original="/img/s1.jpg" /></ul>
            </body></html>""",
        )
    )
    respx.get('https://www.perfectgonzo.com/model/jane').mock(
        return_value=httpx.Response(200, text='<div class="col-md-8 bigmodelpic"><img src="/p/jane.jpg" /></div>')
    )
    detail = await PerfectGonzoClient().fetch_scene_detail('https://www.perfectgonzo.com/movie/7', SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Perfect Gonzo'
    assert detail.tagline == 'All Internal'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['anal']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://www.perfectgonzo.com/p/jane.jpg'
    assert detail.art == ['https://www.perfectgonzo.com/img/p.jpg', 'https://www.perfectgonzo.com/img/s1.jpg']
