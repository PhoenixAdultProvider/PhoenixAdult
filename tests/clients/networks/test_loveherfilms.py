from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.networks.loveherfilms import LoveHerFilmsClient
from app.registry import find_site

SITE = find_site('LoveHerFeet')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search() -> None:
    url = 'https://www.loveherfeet.com/tour/search.php?query=cool+scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text='<div class="item-video-overlay"><a href="/scene/77" title="Cool Scene"></a><p class="video-date">March 4, 2021</p></div>',
        )
    )
    results: list[SearchResult] = []
    await LoveHerFilmsClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://www.loveherfeet.com/scene/77'
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_detail() -> None:
    url = 'https://www.loveherfeet.com/scene/77'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><head><meta property="og:image" content="https://cdn/og.jpg" /></head><body>
              <div class="main-info-left"><h1>Cool Scene</h1></div>
              <p class="description">A summary.</p>
              <div class="date">March 4, 2021</div>
              <div class="video-tags"><a>Footjob</a></div>
              <div class="featured"><a href="/model/jane">Jane Doe</a></div>
              <div class="photos"><a><img src="/img/p1.jpg" /></a></div>
            </body></html>""",
        )
    )
    respx.get('https://www.loveherfeet.com/model/jane').mock(return_value=httpx.Response(200, text='<div class="picture"><img src0_3x="/p/jane.jpg" /></div>'))
    detail = await LoveHerFilmsClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'LoveHerFilms'
    assert detail.tagline == 'LoveHerFeet'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Footjob', 'Foot Sex']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://www.loveherfeet.com/p/jane.jpg'
    assert detail.art == ['https://cdn/og.jpg', 'https://www.loveherfeet.com/img/p1.jpg']
