from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.sites.puba import PubaClient
from phoenixadult.registry import find_site

SITE = find_site('Puba')
assert SITE is not None

DETAIL_HTML = """<html><body>
  <div id="body-player-container">
    <div><div class="tour-video-title">Network Scene</div></div>
    <div><a><img style="background-image: url(https://cdn.puba.com/poster.jpg)"></a></div>
  </div>
  <center><div>
    <a class="btn btn-outline-secondary">Anal</a>
    <a class="btn btn-secondary">Alice</a>
  </div></center>
</body></html>"""


@respx.mock
async def test_search_direct_by_sceneid() -> None:
    url = 'https://www.puba.com/pornstarnetwork/show_video.php?galid=42'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    results: list[SearchResult] = []
    await PubaClient().search(results, SearchContext(title='', encoded='', search_site=SITE.name, site_info=SITE, scene_id='42'))
    assert len(results) == 1
    assert results[0].title == 'Network Scene'
    assert results[0].scene_url == url


@respx.mock
async def test_detail_genres_actors_image() -> None:
    url = 'https://www.puba.com/pornstarnetwork/show_video.php?galid=42'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    detail = await PubaClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Network Scene'
    assert detail.studio == 'Puba'
    assert detail.collections == ['Puba']
    assert detail.genres == ['Anal']
    assert [a.name for a in detail.actors] == ['Alice']
    assert detail.art == ['https://cdn.puba.com/poster.jpg']
