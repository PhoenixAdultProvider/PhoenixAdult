from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext
from app.clients.sites.sexmex import SexMexClient
from app.registry import find_site

SITE = find_site('SexMex')
assert SITE is not None

DETAIL_HTML = """<html><head><meta name="keywords" content="Anal,Latina,Alice"></head><body>
  <h4>The Big Day . Alice</h4>
  <div class="panel-body"><p>A blurb.</p></div>
  <p class="cast"><a href="models/alice.php">Alice</a></p>
  <div class="thumbnail"><img src="https://cdn.sm.com/t1.jpg?token=1"></div>
  <video poster="https://cdn.sm.com/poster.jpg?x=2"></video>
</body></html>"""

ACTOR_HTML = '<html><body><img src="https://cdn.sm.com/alice.jpg"></body></html>'


@respx.mock
async def test_search_cards() -> None:
    url = 'https://sexmex.xxx/tour/search.php?query=big+day'
    html = """<html><body>
      <div class="thumbnail">
        <a href="/tour/scene/big-day"><h5>The Big Day</h5></a>
        <p class="scene-date">2021-04-04</p>
      </div>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results = await SexMexClient().search(SearchContext(title='big day', encoded='big+day', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'The Big Day'
    assert results[0].scene_url == 'https://sexmex.xxx/tour/scene/big-day'
    assert results[0].release_date == '2021-04-04'


@respx.mock
async def test_detail_title_cleanup_genres_actors() -> None:
    url = 'https://sexmex.xxx/tour/scene/big-day'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    respx.get('https://sexmex.xxx/tour/models/alice.php').mock(return_value=httpx.Response(200, text=ACTOR_HTML))
    detail = await SexMexClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    # "The Big Day . Alice" -> actor-name segment sliced off -> "The Big Day"
    assert detail.title == 'The Big Day'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'SexMex'
    assert detail.genres == ['Anal', 'Latina']  # 'Alice' excluded as cast
    assert [a.name for a in detail.actors] == ['Alice']
    assert detail.actors[0].photo_url == 'https://cdn.sm.com/alice.jpg'
    # query strings stripped
    assert detail.raw_image_urls == ['https://cdn.sm.com/t1.jpg', 'https://cdn.sm.com/poster.jpg']
