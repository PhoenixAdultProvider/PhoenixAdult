from __future__ import annotations

from urllib.parse import quote

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites.xillimite import XillimiteClient
from app.registry import find_site

SITE = find_site('Xillimite')
assert SITE is not None


@respx.mock
async def test_search_cards() -> None:
    url = 'https://www.xillimite.com/en/search?type=4&keyword=' + quote('wild scene')
    html = '<html><body><a class="movies" href="/en/scene/wild"><img alt="Wild Scene" src="/thumb.jpg" /></a></body></html>'
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await XillimiteClient().search(results, SearchContext(title='wild scene', encoded=quote('wild scene'), search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Wild Scene'
    assert results[0].scene_url == 'https://www.xillimite.com/en/scene/wild'


@respx.mock
async def test_detail() -> None:
    url = 'https://www.xillimite.com/en/scene/wild'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1>Wild Scene</h1>
              <div id="synopsis">Line one.<br>Line two.</div>
              <div class="casting">
                <div class="slider-xl">
                  <a class="movies"><img alt="Jane Doe" data-src="/img/blur9/jane.jpg" /></a>
                  <a class="movies"><img alt="Mary Roe" data-src="/img/blur9/mary.jpg" /></a>
                </div>
              </div>
              <div class="covers"><a class="cover" href="/img/blur9/c1.jpg">c1</a></div>
              <div class="screenshots">
                <div class="slides">
                  <a href="/img/blur9/s1.jpg">s1</a>
                  <a href="/img/blur9/s2.jpg">s2</a>
                </div>
              </div>
            </body></html>""",
        )
    )
    detail = await XillimiteClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Wild Scene'
    assert detail.summary == 'Line one.\nLine two.'
    assert detail.studio == 'Xillimite'
    assert detail.tagline == 'Xillimite'
    assert detail.collections == ['Xillimite']
    assert [(a.name, a.photo_url) for a in detail.actors] == [
        ('Jane Doe', 'https://www.xillimite.com/img/blur9/jane.jpg'),
        ('Mary Roe', 'https://www.xillimite.com/img/blur9/mary.jpg'),
    ]
    assert detail.raw_image_urls == [
        'https://www.xillimite.com/img//c1.jpg',
        'https://www.xillimite.com/img//s1.jpg',
        'https://www.xillimite.com/img//s2.jpg',
    ]


@respx.mock
async def test_detail_summary_twitter_fallback() -> None:
    url = 'https://www.xillimite.com/en/scene/no-synopsis'
    respx.get(url).mock(
        return_value=httpx.Response(
            200, text='<html><head><meta name="twitter:description" content="Twitter blurb." /></head><body><h1>No Synopsis</h1></body></html>'
        )
    )
    detail = await XillimiteClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.summary == 'Twitter blurb.'
