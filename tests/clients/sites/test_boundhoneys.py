from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.sites.boundhoneys import BoundHoneysClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site

SITE = find_site('Bound Honeys')
assert SITE is not None


@respx.mock
async def test_search_parses_update_cards() -> None:
    url = 'https://boundhoneys.com/search.php?search=wild%20scene'
    html = """<html><body>
      <div class="update">
        <div class="updateTitle"><a href="/scene/wild">Wild Scene</a></div>
      </div>
      <div class="updateDescription">noise</div>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await BoundHoneysClient().search(results, SearchContext(title='wild scene', encoded='wild%20scene', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Wild Scene'
    assert results[0].scene_url == 'https://boundhoneys.com/scene/wild'


@respx.mock
async def test_detail_fields_actors_genres_images() -> None:
    url = 'https://boundhoneys.com/scene/wild'
    html = """<html><head>
      <link rel="preload" href="https://cdn.bh.com/p1.jpg">
      <link rel="preload" href="/p2.jpg">
    </head><body>
      <div class="updateVideoTitle">Wild Scene</div>
      <div class="updateDescription"><b>A blurb.</b></div>
      <div class="updateCategoriesList"><a>Bondage</a><a>BDSM</a></div>
      <div class="updateModelsList"><a href="/model/alice">Alice</a></div>
    </body></html>"""
    actor_html = '<html><body><div class="modelDetailPhoto"><img src="https://cdn.bh.com/alice.jpg"></div></body></html>'
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    respx.get('https://boundhoneys.com/model/alice').mock(return_value=httpx.Response(200, text=actor_html))
    detail = await BoundHoneysClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Wild Scene'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'Bound Honeys'
    assert detail.collections == ['Bound Honeys']
    assert detail.genres == ['Bondage', 'BDSM']
    assert len(detail.actors) == 1
    assert detail.actors[0].name == 'Alice'
    assert detail.actors[0].photo_url == 'https://cdn.bh.com/alice.jpg'
    assert detail.art == ['https://cdn.bh.com/p1.jpg', 'https://boundhoneys.com/p2.jpg']
