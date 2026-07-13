from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites.penthousegold import PenthouseGoldClient
from app.registry import find_site

SITE = find_site('Penthouse Gold')
assert SITE is not None

DETAIL_HTML = """<html><head><meta itemprop="uploadDate" content="07/07/2021"></head><body>
  <div class="content-desc content-new-scene"><h1>Video - Gold Night</h1><p>A blurb.</p></div>
  <ul class="scene-tags"><li><a>Glamour</a></li><li><a>Solo</a></li></ul>
  <ul id="featured_pornstars"><div class="model"><h3>Alice</h3><img src="https://cdn.pg.com/alice.jpg"></div></ul>
  <div id="trailer_player_finished"><img src="https://cdn.pg.com/poster.jpg"></div>
</body></html>"""


@respx.mock
async def test_search_onsite_and_guess() -> None:
    search_url = 'https://penthousegold.com/search.php?query=gold%20night'
    respx.get(search_url).mock(return_value=httpx.Response(200, text='<html><body></body></html>'))
    video_url = 'https://penthousegold.com/scenes/video---gold-night_vids.html'
    respx.get(video_url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    respx.get('https://penthousegold.com/scenes/movie---gold-night_vids.html').mock(return_value=httpx.Response(404))
    results: list[SearchResult] = []
    await PenthouseGoldClient().search(results, SearchContext(title='gold night', encoded='gold%20night', search_site=SITE.name, site_info=SITE))
    assert any(r.scene_url == video_url for r in results)
    hit = next(r for r in results if r.scene_url == video_url)
    assert hit.title == 'Video - Gold Night'
    assert hit.score == 100
    assert hit.release_date == '2021-07-07'


@respx.mock
async def test_detail_fields_actors_images() -> None:
    url = 'https://penthousegold.com/scenes/video---gold-night_vids.html'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    detail = await PenthouseGoldClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Gold Night'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'Penthouse Gold'
    assert detail.release_date == '2021-07-07'
    assert detail.genres == ['glamour', 'solo']
    assert [a.name for a in detail.actors] == ['Alice']
    assert detail.actors[0].photo_url == 'https://cdn.pg.com/alice.jpg'
    assert detail.raw_image_urls == ['https://cdn.pg.com/poster.jpg']
