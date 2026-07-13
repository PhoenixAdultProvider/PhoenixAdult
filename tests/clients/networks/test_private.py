from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.networks.private import PrivateClient, _lang_headers
from app.registry import find_site

SITE = find_site('Private')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


def test_lang_headers() -> None:
    assert _lang_headers('de') == {'Accept-Language': 'de'}
    assert _lang_headers('en-US') == {'Accept-Language': 'en'}
    assert _lang_headers('jp') == {}
    assert _lang_headers(None) == {}


@respx.mock
async def test_search() -> None:
    url = 'https://www.private.com/search.php?query=cool+scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text='<ul id="search_results"><li class="card"><h3><a href="/scene/7">Cool Scene</a></h3><span class="scene-date">March 4, 2021</span></li></ul>',
        )
    )
    results: list[SearchResult] = []
    await PrivateClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://www.private.com/scene/7'
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_detail() -> None:
    url = 'https://www.private.com/scene/7'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><head>
              <meta itemprop="description" content="A summary." />
              <meta itemprop="uploadDate" content="2021-03-04" />
              <meta itemprop="thumbnailUrl" content="https://cdn/thumb.jpg?t=1" />
              <meta itemprop="contentURL" content="https://pcoms.cdn/upload/abc/scene99/trailers/x.mp4" />
              </head><body>
              <h1>Cool Scene</h1>
              <li class="tag-sites"><a>Private MILFs</a></li>
              <li class="tag-tags"><a>Anal</a></li>
              <li class="tag-models"><a href="/model/jane">Jane Doe</a></li>
            </body></html>""",
        )
    )
    respx.get('https://www.private.com/model/jane').mock(
        return_value=httpx.Response(200, text='<img srcset="https://cdn/a.jpg 1x, https://cdn/jane-big.jpg 2x" />')
    )
    respx.get(url__startswith='https://www.private.com/gallery.php').mock(return_value=httpx.Response(200, text='<a href="https://cdn/g1.jpg?z=1"></a>'))
    detail = await PrivateClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Private'
    assert detail.tagline == 'Private MILFs'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['anal']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://cdn/jane-big.jpg'
    assert 'https://cdn/thumb.jpg?t=1' in detail.raw_image_urls
    assert 'https://cdn/g1.jpg?z=1' in detail.raw_image_urls
    assert 'https://pcom.cdn/upload/abc/scene99/Fullwatermarked/scene99_005.jpg' in detail.raw_image_urls
