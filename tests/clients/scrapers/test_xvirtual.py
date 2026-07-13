from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites.xvirtual import XVirtualClient
from app.registry import find_site

SITE = find_site('XVirtual')
assert SITE is not None


@respx.mock
async def test_search_parses_episode_rows() -> None:
    url = 'https://xvirtual.com/tour/search/?q=wild%20scene'
    html = """<html><body>
      <div class="episode-list"><div class="episode">
        <a href="/scene/wild">x</a><h2>Wild Scene</h2>
      </div></div>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await XVirtualClient().search(results, SearchContext(title='wild scene', encoded='wild%20scene', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Wild Scene'
    assert results[0].scene_url == 'https://xvirtual.com/scene/wild'


@respx.mock
async def test_detail_images_genres_no_actors() -> None:
    url = 'https://xvirtual.com/scene/wild'
    html = """<html><head>
      <meta property="og:image" content="https://cdn.xv.com/og.jpg?ts=1">
    </head><body>
      <div class="title"><h2>Wild Scene</h2></div>
      <div class="description"><div class="desc-text">A blurb.</div></div>
      <ul class="tags"><a>VR</a><a>POV</a></ul>
      <div class="thumbnails"><img src="https://cdn.xv.com/t1.jpg?v=2"><img src="https://cdn.xv.com/t2.jpg"></div>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    detail = await XVirtualClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Wild Scene'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'XVirtual'
    assert detail.genres == ['VR', 'POV']
    assert detail.actors == []
    assert detail.raw_image_urls == ['https://cdn.xv.com/og.jpg', 'https://cdn.xv.com/t1.jpg', 'https://cdn.xv.com/t2.jpg']
