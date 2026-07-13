from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites.amourangels import AmourAngelsClient
from app.registry import find_site

SITE = find_site('Amour Angels')
assert SITE is not None

DETAIL_HTML = """<html><body>
  <table><tr><td class="blox-bg">
    <table><tr>
      <td>label</td>
      <td><b>Video Sunny Day</b> Added 2021-05-10 by editor</td>
    </tr></table>
  </td></tr></table>
  <td class="modinfo"><a href="/model_anna.html">Anna</a></td>
  <td class="noisebg"><div><img src="https://cdn.aa.com/p1.jpg"><img src="/p2.jpg"></div></td>
</body></html>"""

ACTOR_HTML = """<html><body>
  <td class="modelinfo-bg"><table><tr><td><img src="https://cdn.aa.com/anna.jpg"></td></tr></table></td>
</body></html>"""


@respx.mock
async def test_search_direct_url_single_result() -> None:
    url = 'https://amourangels.com/z_cover_sunny day.html'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    results: list[SearchResult] = []
    await AmourAngelsClient().search(results, SearchContext(title='sunny day', encoded='sunny%20day', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Sunny Day'
    assert results[0].scene_url == url
    assert results[0].score == 100


@respx.mock
async def test_detail_fields_actors_images() -> None:
    url = 'https://amourangels.com/z_cover_sunny.html'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    respx.get('https://amourangels.com/model_anna.html').mock(return_value=httpx.Response(200, text=ACTOR_HTML))
    detail = await AmourAngelsClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Sunny Day'
    assert detail.studio == 'Amour Angels'
    assert detail.collections == ['Amour Angels']
    assert detail.genres == ['Softcore', 'European Girls']
    assert detail.release_date == '2021-05-10'
    assert len(detail.actors) == 1
    assert detail.actors[0].name == 'anna'
    assert detail.actors[0].photo_url == 'https://cdn.aa.com/anna.jpg'
    assert detail.actors[0].gender == 'female'
    assert detail.raw_image_urls == ['https://cdn.aa.com/p1.jpg', 'https://amourangels.com/p2.jpg']
