from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.networks.littlecaprice import LittleCapriceClient
from phoenixadult.registry import find_site

SITE = find_site('Little Caprice Dreams')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search() -> None:
    url = 'https://www.littlecaprice-dreams.com/?s=cool+scene'
    html = (
        '<div id="left-area"><article>'
        '<h2 class="entry-title"><a href="/scene/cool">Cool Scene</a></h2>'
        '<span class="published">March 4, 2021</span></article></div>'
    )
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await LittleCapriceClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://www.littlecaprice-dreams.com/scene/cool'
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_detail_two_hop() -> None:
    gallery_url = 'https://www.littlecaprice-dreams.com/scene/cool'
    respx.get(gallery_url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><head><meta property="og:image" content="https://cdn/gallery-og.jpg" /></head><body>
              <a class="et_pb_button button" href="/g">Gallery</a>
              <a class="et_pb_button button" href="/video/cool">Video</a>
              <div class="project-tags"><div class="list"><a>Anal</a></div></div>
              <div class="gallery spotlight-group"><img src="/img/g1.jpg" /></div>
            </body></html>""",
        )
    )
    respx.get('https://www.littlecaprice-dreams.com/video/cool').mock(
        return_value=httpx.Response(
            200,
            text="""<html><head><meta property="og:image" content="https://cdn/video-og.jpg" /></head><body>
              <div id="main-project-content" class="post category_buttmuse">
                <div class="project-details"><h1>Buttmuse Cool Scene</h1></div>
                <div class="desc-text">A summary.</div>
                <div class="relese-date">Release: March 4, 2021</div>
                <div class="project-tags"><div class="list"><a>Toys</a></div></div>
                <div class="project-models"><a href="/model/jane">Jane Doe</a></div>
              </div>
            </body></html>""",
        )
    )
    respx.get('https://www.littlecaprice-dreams.com/model/jane').mock(return_value=httpx.Response(200, text='<img class="img-poster" src="/p/jane.jpg" />'))
    detail = await LittleCapriceClient().fetch_scene_detail(gallery_url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'LittleCaprice'
    assert detail.tagline == 'Buttmuse'
    assert detail.release_date == '2021-03-04'
    assert 'toys' in detail.genres and 'anal' in detail.genres
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://www.littlecaprice-dreams.com/p/jane.jpg'
    assert 'https://cdn/video-og.jpg' in detail.art
    assert 'https://www.littlecaprice-dreams.com/img/g1.jpg' in detail.art
