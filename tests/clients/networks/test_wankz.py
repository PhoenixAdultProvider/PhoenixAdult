from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.networks.wankz import WankzClient
from app.registry import find_site

SITE = find_site('Wankz TV')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search() -> None:
    html = (
        '<div class="scene"><a href="/v/7"></a>'
        '<div class="title-wrapper"><a class="title">Cool Scene</a></div>'
        '<div class="series-container"><a class="sitename">Wankz TV</a></div></div>'
    )
    respx.get('https://wankz.com/search?q=cool+scene').mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await WankzClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://wankz.com/v/7'
    assert results[0].score is not None and results[0].score > 0
    assert results[0].subsite == 'Wankz TV'


@respx.mock
async def test_detail() -> None:
    url = 'https://wankz.com/v/7'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <div class="title"><h1>Cool Scene</h1></div>
              <div class="description"><p>A summary.</p></div>
              <div class="views"><span>Added March 4, 2021</span></div>
              <a class="cat">Teen</a>
              <div class="actors"><a class="model"><span>Jane Doe</span><img src="/p/jane.jpg" /></a></div>
              <a class="noplayer"><img src="/img/c.jpg" /></a>
            </body></html>""",
        )
    )
    detail = await WankzClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Wankz'
    assert detail.collections == ['Wankz']
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Teen']
    assert detail.actors is not None and detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == '/p/jane.jpg'  # actor photos kept raw (TS parity)
    assert detail.art == ['https://wankz.com/img/c.jpg']
