from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites.darkroomvr import DarkRoomVRClient
from app.registry import find_site

SITE = find_site('DarkRoomVR')
assert SITE is not None


@respx.mock
async def test_search_parses_cards() -> None:
    url = 'https://darkroomvr.com/search?q=wild%20scene'
    html = """<html><body>
      <a class="video-card__item" href="/scene/wild">
        <div class="video-card__title">Wild Scene</div>
      </a>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await DarkRoomVRClient().search(results, SearchContext(title='wild scene', encoded='wild%20scene', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Wild Scene'
    assert results[0].scene_url == 'https://darkroomvr.com/scene/wild'


@respx.mock
async def test_detail_fields_actors_genres_images() -> None:
    url = 'https://darkroomvr.com/scene/wild'
    html = """<html><body>
      <h1>Wild Scene</h1>
      <div data-id="description" class="hidden">A blurb. Read less</div>
      <div class="video-info__time">VR • 2021-07-04</div>
      <a class="tags__item">VR</a><a class="tags__item">POV</a>
      <div class="video-info__text"><a href="/star/alice">Alice</a></div>
      <div class="video-detail__gallery-item"><a href="https://cdn.dr.com/g1.jpg">x</a></div>
      <div class="video-detail__gallery-item"><a href="/g2.jpg">x</a></div>
    </body></html>"""
    actor_html = '<html><body><img class="pornstar-detail__picture" src="https://cdn.dr.com/alice.jpg"></body></html>'
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    respx.get('https://darkroomvr.com/star/alice').mock(return_value=httpx.Response(200, text=actor_html))
    detail = await DarkRoomVRClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Wild Scene'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'DarkRoomVR'
    assert detail.collections == ['DarkRoomVR']
    assert detail.release_date == '2021-07-04'
    assert detail.genres == ['VR', 'POV']
    assert len(detail.actors) == 1
    assert detail.actors[0].name == 'Alice'
    assert detail.actors[0].photo_url == 'https://cdn.dr.com/alice.jpg'
    assert detail.raw_image_urls == ['https://cdn.dr.com/g1.jpg', 'https://darkroomvr.com/g2.jpg']
