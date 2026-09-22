from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.networks.sinx import SinXClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site

SITE = find_site('Slime Wave')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search() -> None:
    url = 'https://sinx.com/videos/all?sexualOrientation=0&searchWord=cool+scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200, text='<div class="view_grid--container"><div class="video_item--content"><a href="/v/7" title="Cool Scene"></a></div></div>'
        )
    )
    results: list[SearchResult] = []
    await SinXClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://sinx.com/v/7'


@respx.mock
async def test_detail() -> None:
    url = 'https://sinx.com/v/7'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1 class="title--3">Cool Scene</h1>
              <div><h5>About</h5><p>A summary.</p></div>
              <table><tr><td>Date</td><td>04 Mar 2021</td></tr></table>
              <div class="tags-wrap"><a>#pissing</a></div>
              <div class="video__block video_item--player"><img src="https://cdn/p.jpg" /></div>
              <figure class="girls-item"><figcaption><h4>Jane Doe</h4></figcaption><div><img src="https://cdn/jane.jpg" /></div></figure>
            </body></html>""",
        )
    )
    detail = await SinXClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'SinX'
    assert detail.tagline == 'Slime Wave'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['pissing']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://cdn/jane.jpg'
    assert detail.art == ['https://cdn/p.jpg']
