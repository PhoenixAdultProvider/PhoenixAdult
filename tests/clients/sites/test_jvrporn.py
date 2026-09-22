from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.sites.jvrporn import JVRPornClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site

SITE = find_site('JVR Porn')
assert SITE is not None

DETAIL_HTML = """<html><body>
  <h1>VR Adventure</h1>
  <pre>A blurb.</pre>
  <td class="video-tags"><span>VR</span><span>POV</span></td>
  <a class="actress"><span>Alice</span></a>
  <div id="snapshot-gallery"><a href="https://cdn.jvr.com/s1.jpg">x</a></div>
  <deo-video cover-image="/cover.jpg"></deo-video>
</body></html>"""


@respx.mock
async def test_search_direct_by_sceneid() -> None:
    url = 'https://jvrporn.com/video/321'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    results: list[SearchResult] = []
    await JVRPornClient().search(results, SearchContext(title='', encoded='', search_site=SITE.name, site_info=SITE, scene_id='321'))
    assert len(results) == 1
    assert results[0].title == 'VR Adventure'
    assert results[0].scene_url == url
    assert results[0].score == 100


@respx.mock
async def test_detail_fields_genres_actors_images() -> None:
    url = 'https://jvrporn.com/video/321'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    detail = await JVRPornClient().fetch_scene_detail(f'{url}|2021-03-03', SITE)
    assert detail is not None
    assert detail.title == 'VR Adventure'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'JVR Porn'
    assert detail.collections == ['JVR Porn']
    assert detail.release_date == '2021-03-03'
    assert detail.genres == ['VR', 'POV']
    assert [a.name for a in detail.actors] == ['Alice']
    assert detail.art == ['https://cdn.jvr.com/s1.jpg', 'https://jvrporn.com/cover.jpg']
