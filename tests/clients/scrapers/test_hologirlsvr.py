from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext
from app.clients.sites.hologirlsvr import HoloGirlsVRClient
from app.registry import find_site

SITE = find_site('HoloGirlsVR')
assert SITE is not None

DETAIL_HTML = """<html><body>
  <div class="video-title"><h3>Holo Scene</h3></div>
  <div class="vidpage-info">a<br>b<br>c<br>d<br>A blurb here<br>f</div>
  <div class="videopage-tags"><a>VR</a><a>POV</a></div>
  <div class="col-md-3">
    <img class="imgHover" src="/img/alice.jpg">
    <div class="vidpage-mobilePad"><a><strong>Alice</strong></a></div>
  </div>
  <div class="vidCover"><img src="https://cdn.hg.com/cover.jpg"></div>
  <div class="vid-flex-container"><span><img src="/img/s1_thumb.jpg"></span></div>
</body></html>"""


@respx.mock
async def test_search_direct_by_sceneid() -> None:
    url = 'https://www.hologirlsvr.com/Scenes/Videos/555'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    results = await HoloGirlsVRClient().search(SearchContext(title='', encoded='', search_site=SITE.name, site_info=SITE, scene_id='555'))
    assert len(results) == 1
    assert results[0].title == 'Holo Scene'
    assert results[0].scene_url == url
    assert results[0].score == 100


@respx.mock
async def test_search_on_site_cards() -> None:
    url = 'https://www.hologirlsvr.com/Scenes?back=1&search=holo'
    html = """<html><body>
      <div class="memVid"><div class="memVidTitle"><a href="/Scenes/Videos/9" title="Holo Nine">x</a></div></div>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results = await HoloGirlsVRClient().search(SearchContext(title='holo', encoded='holo', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Holo Nine'
    assert results[0].scene_url == 'https://www.hologirlsvr.com/Scenes/Videos/9'


@respx.mock
async def test_detail_summary_genres_actors_images() -> None:
    url = 'https://www.hologirlsvr.com/Scenes/Videos/555'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    detail = await HoloGirlsVRClient().fetch_scene_detail(f'{url}|2021-10-10', SITE)
    assert detail is not None
    assert detail.title == 'Holo Scene'
    assert detail.summary == 'A blurb here'
    assert detail.studio == 'HoloGirlsVR'
    assert detail.collections == ['HoloGirlsVR']
    assert detail.release_date == '2021-10-10'
    assert detail.genres == ['VR', 'POV']
    assert [a.name for a in detail.actors] == ['Alice']
    assert detail.actors[0].photo_url == 'https://www.hologirlsvr.com/img/alice.jpg'
    assert detail.raw_image_urls == ['https://cdn.hg.com/cover.jpg', 'https://www.hologirlsvr.com/img/s1.jpg']
