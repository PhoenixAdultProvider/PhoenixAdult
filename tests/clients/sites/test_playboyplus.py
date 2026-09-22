from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.sites.playboyplus import PlayboyPlusClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site
from phoenixadult.utils.helpers.helpers import pack_cur_id

SITE = find_site('Playboy Plus')
assert SITE is not None

DETAIL_HTML = """<html><body>
  <h1 class="title">Golden Hour</h1>
  <p class="description-truncated">A blurb...</p>
  <p class="date">March 3, 2021</p>
  <p class="contributorName"><a>Alice</a></p>
  <img class="lazy image" data-src="https://cdn.pp.com/main.jpg?w=100">
  <section class="gallery"><img class="image" data-src="https://cdn.pp.com/g1.jpg?x=1"></section>
</body></html>"""


@respx.mock
async def test_search_cards() -> None:
    url = 'https://www.playboyplus.com/search/golden'
    html = """<html><body>
      <img class="image" data-src="https://cdn.pp.com/poster.jpg?w=50">
      <div id="search-results-gallery"><li class="item">
        <h3 class="title">Golden Hour</h3>
        <a class="cardLink" href="/scene/golden">x</a>
        <p class="date">2021-03-03</p>
      </li></div>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await PlayboyPlusClient().search(results, SearchContext(title='golden', encoded='golden', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Golden Hour'
    assert results[0].scene_url == 'https://www.playboyplus.com/scene/golden'
    assert results[0].release_date == '2021-03-03'


@respx.mock
async def test_detail_via_packed_curid() -> None:
    scene_url = 'https://www.playboyplus.com/scene/golden'
    respx.get(scene_url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    cur_id = pack_cur_id([scene_url, 'https://cdn.pp.com/poster.jpg'])
    detail = await PlayboyPlusClient().fetch_scene_detail(PlayboyPlusClient().decode(cur_id), SITE)
    assert detail is not None
    assert detail.title == 'Golden Hour'
    assert detail.summary == 'A blurb'
    assert detail.studio == 'Playboy Plus'
    assert detail.release_date == '2021-03-03'
    assert detail.genres == ['Glamour']
    assert [a.name for a in detail.actors] == ['Alice']
    assert detail.art == ['https://cdn.pp.com/poster.jpg', 'https://cdn.pp.com/main.jpg', 'https://cdn.pp.com/g1.jpg']
