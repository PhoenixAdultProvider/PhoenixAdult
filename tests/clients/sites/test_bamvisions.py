from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.sites.bamvisions import BAMVisionsClient
from phoenixadult.registry import find_site

SITE = find_site('BAMVisions')
assert SITE is not None


@respx.mock
async def test_search_parses_cards() -> None:
    url = 'https://tour.bamvisions.com/search.php?st=advanced&qall=wild%20scene'
    html = """<html><body>
      <div class="category_listing_wrapper_updates">
        <h3><a href="/scene/wild">Wild Scene</a></h3>
      </div>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await BAMVisionsClient().search(results, SearchContext(title='wild scene', encoded='wild%20scene', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Wild Scene'
    assert results[0].scene_url == 'https://tour.bamvisions.com/scene/wild'


@respx.mock
async def test_detail_fields_actors_images() -> None:
    url = 'https://tour.bamvisions.com/scene/wild'
    html = """<html><body>
      <div class="item-info">
        <h4><a>Wild Scene</a></h4>
        <h5><a href="/model/alice">Alice</a></h5>
      </div>
      <p class="description">A blurb.</p>
      <ul class="item-meta"><li>Release Date: January 5, 2021</li></ul>
      <img class="x update_thumb" src0_3x="https://cdn.bv.com/t1.jpg">
      <img class="update_thumb" src0_3x="/t2.jpg">
    </body></html>"""
    actor_html = '<html><body><div class="profile-pic"><img src0_3x="https://cdn.bv.com/alice.jpg"></div></body></html>'
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    respx.get('https://tour.bamvisions.com/model/alice').mock(return_value=httpx.Response(200, text=actor_html))
    detail = await BAMVisionsClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Wild Scene'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'BAMVisions'
    assert detail.collections == ['BAMVisions']
    assert detail.genres == ['Anal', 'Hardcore']
    assert detail.release_date == '2021-01-05'
    assert len(detail.actors) == 1
    assert detail.actors[0].name == 'Alice'
    assert detail.actors[0].photo_url == 'https://cdn.bv.com/alice.jpg'
    assert detail.art == ['https://cdn.bv.com/t1.jpg', 'https://tour.bamvisions.com/t2.jpg']
