from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.networks.gasm import GasmClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site

SITE = find_site('GASM')
MAGMA = find_site('Magma Film')
assert SITE is not None and MAGMA is not None


def _ctx(site: object, title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '%20'), search_site=site.name, site_info=site, **kw)  # type: ignore[union-attr,arg-type]


@respx.mock
async def test_search_direct_scene_id() -> None:
    url = 'https://www.gasm.com/post/details/555'
    respx.get(url).mock(return_value=httpx.Response(200, text='<h1 class="post_title"><span>Cool Scene</span></h1><h3 class="post_date">Mar 4, 2021</h3>'))
    results: list[SearchResult] = []
    await GasmClient().search(results, _ctx(SITE, scene_id='555'))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == url
    assert results[0].score == 100
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_search_keyword_with_channel() -> None:
    url = 'https://www.gasm.com/search/videos?s=cool+scene&channel=8118'
    respx.get(url).mock(return_value=httpx.Response(200, text='<div class="results_item"><a class="post_title" href="/post/details/77">Cool Scene</a></div>'))
    results: list[SearchResult] = []
    await GasmClient().search(results, _ctx(MAGMA))
    assert len(results) == 1
    assert results[0].scene_url == 'https://www.gasm.com/post/details/77'


@respx.mock
async def test_detail() -> None:
    url = 'https://www.gasm.com/post/details/77'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><head><meta name="twitter:image" content="https://cdn/og.jpg" /></head><body>
              <h1 class="post_title"><span>Cool Scene</span></h1>
              <h2 class="post_description">A summary.</h2>
              <h3 class="post_date">Mar 4, 2021</h3>
              <a href="/studio/profile/5">cool studio</a>
              <div class="post_item dvd"><h1>cool dvd</h1></div>
              <a href="/search?s=anal">Anal</a>
              <a href="/models/jane">Jane Doe</a>
              <img class="item_cover" src="/img/c.jpg" />
            </body></html>""",
        )
    )
    detail = await GasmClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'GASM'
    assert detail.tagline == 'Cool Studio'
    assert detail.collections == ['Cool Studio', 'Cool Dvd']
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Anal']
    assert [a.name for a in detail.actors] == ['Jane Doe']
    assert detail.art == ['https://www.gasm.com/img/c.jpg', 'https://cdn/og.jpg']
