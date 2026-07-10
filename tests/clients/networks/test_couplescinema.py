from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext
from app.clients.networks.couplescinema import CouplesCinemaClient
from app.registry import find_site

SITE = find_site('JoyBear')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '%20'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search_direct_scene_id() -> None:
    url = 'https://www.couplescinema.com/post/details/555'
    respx.get(url).mock(return_value=httpx.Response(200, text='<div class="mediaHeader"><span class="title">Cool Scene</span></div>'))
    results = await CouplesCinemaClient().search(_ctx(scene_id='555'))
    assert len(results) == 1
    assert results[0].scene_url == url
    assert results[0].title == 'Cool Scene'
    assert results[0].score == 100


@respx.mock
async def test_search_keyword_packs_cover() -> None:
    url = 'https://www.couplescinema.com/search/videos?s=cool+scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<div class="Post_x">
              <span class="title_x">Cool Scene</span>
              <a class="media_x" href="/post/details/77"><img class="image_x" src="https://cdn/cover.jpg" /></a>
              <span class="source_x">JoyBear</span>
            </div>""",
        )
    )
    results = await CouplesCinemaClient().search(_ctx(search_date='2021-03-04'))
    assert len(results) == 1
    assert results[0].scene_url == 'https://www.couplescinema.com/post/details/77'
    assert results[0].score == 100
    detail_html = '<video poster="https://cdn/poster.jpg"></video>'
    respx.get('https://www.couplescinema.com/post/details/77').mock(return_value=httpx.Response(200, text=detail_html))
    detail = await CouplesCinemaClient().fetch_scene_detail(CouplesCinemaClient().decode(results[0].cur_id), SITE)
    assert detail is not None
    assert detail.raw_image_urls == ['https://cdn/cover.jpg', 'https://cdn/poster.jpg']


@respx.mock
async def test_detail_fields() -> None:
    url = 'https://www.couplescinema.com/post/details/77'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <div class="mediaHeader"><span class="title">Cool Scene</span></div>
              <span class="description">A summary.</span>
              <span class="type">Feature | 2021 | 90min</span>
              <div class="cast"><a>Jane Doe</a><a>John Smith</a></div>
              <video poster="https://cdn/poster.jpg"></video>
            </body></html>""",
        )
    )
    detail = await CouplesCinemaClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Couples Cinema'
    assert detail.tagline == 'Feature'
    assert detail.collections == ['Feature']
    assert detail.release_date == '2021-01-01'
    assert [a.name for a in detail.actors] == ['Jane Doe', 'John Smith']
    assert detail.raw_image_urls == ['https://cdn/poster.jpg']
