from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.sites.pjgirls import PJGirlsClient
from phoenixadult.registry import find_site

SITE = find_site('PJGirls')
assert SITE is not None

DETAIL_HTML = """<html><head><title>Speculum Show - porn video | PJGirls</title></head><body>
  <div class="text"><p>A blurb.</p></div>
  <div class="info">
    <h3>March 5, 2021</h3>
    <h3>length</h3>
    <h3><a href="/models/alice">Alice</a></h3>
  </div>
  <div class="detailTagy clear"><a>Solo</a><a>Speculum</a></div>
  <div class="videoObal"><img src="https://cdn.pj.com/p1.jpg"></div>
</body></html>"""

ACTOR_HTML = '<html><body><div class="image"><img src="https://cdn.pj.com/alice.jpg"></div></body></html>'


@respx.mock
async def test_search_cards() -> None:
    url = 'http://www.pjgirls.com/en/videos/?fulltext=speculum'
    html = """<html><body>
      <div class="thumb video">
        <h2>Speculum Show</h2>
        <a href="/scene/speculum"><div><span>x</span><span>2021-03-05</span></div></a>
      </div>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await PJGirlsClient().search(results, SearchContext(title='speculum', encoded='speculum', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Speculum Show'
    assert results[0].scene_url == 'http://www.pjgirls.com/scene/speculum'
    assert results[0].release_date == '2021-03-05'


@respx.mock
async def test_detail_fields_actors_images() -> None:
    url = 'http://www.pjgirls.com/scene/speculum'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    respx.get('http://www.pjgirls.com/models/alice').mock(return_value=httpx.Response(200, text=ACTOR_HTML))
    detail = await PJGirlsClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Speculum Show'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'PJGirls'
    assert detail.collections == ['PJGirls']
    assert detail.release_date == '2021-03-05'
    assert detail.genres == ['Solo', 'Speculum']
    assert [a.name for a in detail.actors] == ['Alice']
    assert detail.actors[0].photo_url == 'https://cdn.pj.com/alice.jpg'
    assert detail.art == ['https://cdn.pj.com/p1.jpg']
