from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.networks.wankzvr import WankzVRClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site

SITE = find_site('WankzVR')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '%20'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_direct_scene() -> None:
    respx.get('https://www.wankzvr.com/12345').mock(
        return_value=httpx.Response(200, text='<h1 class="detail__title">Cool Scene</h1><span class="detail__date">March 4, 2021</span>')
    )
    results: list[SearchResult] = []
    await WankzVRClient().search(results, _ctx(title='12345'))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].score == 100
    assert results[0].scene_url == 'https://www.wankzvr.com/12345'


@respx.mock
async def test_search() -> None:
    html = (
        '<ul class="cards-list"><li><a href="/v/7"></a>'
        '<div class="card__footer"><div class="card__h">Cool Scene<span>x</span></div></div>'
        '<div class="card__date">March 4, 2021</div></li></ul>'
    )
    respx.get('https://www.wankzvr.com/search?q=cool+scene').mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await WankzVRClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://www.wankzvr.com/v/7'


@respx.mock
async def test_detail() -> None:
    url = 'https://www.wankzvr.com/v/7'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><head></head><body>
              <h1 class="detail__title">Cool Scene</h1>
              <div class="detail__txt">A summary.</div>
              <span class="detail__date">March 4, 2021</span>
              <div class="tag-list"><a>Teen</a></div>
              <div class="detail__models"><a href="/girl/jane">Jane Doe</a></div>
              <meta property="og:image" content="https://cdn/cover_medium.jpg" />
            </body></html>""",
        )
    )
    respx.get('https://www.wankzvr.com/girl/jane').mock(
        return_value=httpx.Response(
            200,
            text='<html><head></head><body><div class="person__avatar"><source srcset="a.webp" /><source srcset="https://cdn/jane.webp" /></div></body></html>',
        )
    )
    detail = await WankzVRClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'WankzVR'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Teen']
    assert detail.actors is not None and detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://cdn/jane.jpg'
    assert detail.art == ['https://cdn/hero_large.jpg']
