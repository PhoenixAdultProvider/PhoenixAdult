from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext
from app.clients.sites.realitylovers import RealityLoversClient
from app.registry import find_site

SITE = find_site('Reality Lovers')
assert SITE is not None

SEARCH_API = 'https://realitylovers.com/videos/search'
SEARCH_BODY = {'contents': [{'title': 'VR Dream', 'videoUri': 'video/vr-dream', 'released': '2021-05-05'}]}

DETAIL_HTML = """<html><body>
  <h1 class="video-detail-name">VR Dream</h1>
  <p itemprop="description">A blurb.   Read more…</p>
  <span class="videoClip__Details-infoValue">2021-05-05</span>
  <span itemprop="keywords"><a>VR</a><a>POV</a></span>
  <span itemprop="actors"><a href="https://realitylovers.com/girl/alice">Alice</a></span>
  <img class="videoClip__Details--galleryItem" data-big="https://cdn.rl.com/s1_small.jpg 960w,https://cdn.rl.com/s1_big.jpg 1920w">
</body></html>"""

ACTOR_HTML = '<html><body><img class="girlDetails-posterImage" srcset="https://cdn.rl.com/a_s.jpg 1x,https://cdn.rl.com/alice.jpg 2x"></body></html>'


@respx.mock
async def test_search_json_post() -> None:
    respx.post(SEARCH_API).mock(return_value=httpx.Response(200, json=SEARCH_BODY))
    results = await RealityLoversClient().search(SearchContext(title='vr dream', encoded='vr%20dream', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'VR Dream'
    assert results[0].scene_url == 'https://realitylovers.com/video/vr-dream'
    assert results[0].release_date == '2021-05-05'


@respx.mock
async def test_detail_srcset_actors_images() -> None:
    url = 'https://realitylovers.com/video/vr-dream'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    respx.get('https://realitylovers.com/girl/alice').mock(return_value=httpx.Response(200, text=ACTOR_HTML))
    detail = await RealityLoversClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'VR Dream'
    assert detail.summary == 'A blurb.'  # '…' and 'Read more' stripped, whitespace collapsed
    assert detail.studio == 'Reality Lovers'
    assert detail.release_date == '2021-05-05'
    assert detail.genres == ['vr', 'pov']
    assert [a.name for a in detail.actors] == ['Alice']
    # actor srcset index-1 entry minus the 3-char " 2x" descriptor, https->http
    assert detail.actors[0].photo_url == 'http://cdn.rl.com/alice.jpg'
    # gallery last entry minus the 6-char " 1920w" descriptor, https->http
    assert detail.raw_image_urls == ['http://cdn.rl.com/s1_big.jpg']
