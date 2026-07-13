from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.networks.kink import KinkClient, _kink_tagline
from app.registry import find_site

SITE = find_site('Kink')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search_direct_scene_id() -> None:
    url = 'https://www.kink.com/shoot/555'
    respx.get(url).mock(return_value=httpx.Response(200, text='<h1 class="fs-0">Cool Scene</h1>'))
    results: list[SearchResult] = []
    await KinkClient().search(results, _ctx(scene_id='555'))
    assert len(results) == 1
    assert results[0].scene_url == url
    assert results[0].title == 'Cool Scene'
    assert results[0].score == 100


@respx.mock
async def test_detail() -> None:
    url = 'https://www.kink.com/shoot/555'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1 class="fs-0">Cool Scene</h1>
              <div class="description"><span class="fw-200">A<br>summary.</span></div>
              <div class="shoot-detail-legend">
                <a href="/channel/hogtied">Hogtied</a>
                <span class="text-muted ms-2">March 4, 2021</span>
              </div>
              <a href="/tag/bondage">Bondage,</a>
              <span class="text-primary"><a href="/model/jane">Jane Doe</a></span>
              <span class="director-name"><a href="/model/dir">Director</a></span>
              <video poster="https://cdn/poster.jpg?token=x"></video>
            </body></html>""",
        )
    )
    respx.get('https://www.kink.com/model/jane').mock(
        return_value=httpx.Response(200, text='<div class="biography-container"><img src="https://cdn/jane.jpg" /></div>')
    )
    respx.get('https://www.kink.com/model/dir').mock(return_value=httpx.Response(200, text='<div></div>'))
    detail = await KinkClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.tagline == 'Hogtied'
    assert detail.studio == 'Kink'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Bondage']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://cdn/jane.jpg'
    assert detail.directors is not None and detail.directors[0].name == 'Director'
    assert detail.art == ['https://cdn/poster.jpg?token=x']


def test_kink_tagline() -> None:
    assert _kink_tagline('Whipped Ass /channel/whippedass', 'Kink') == 'Whipped Ass'
    assert _kink_tagline('Strapon Squad /channel/straponsquad', 'Kink') == 'Strapon Squad'
    assert _kink_tagline('Unknown', 'Kink') == 'Kink'
