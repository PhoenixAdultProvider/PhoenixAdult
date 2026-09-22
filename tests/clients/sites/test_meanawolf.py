from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.sites.meanawolf import MeanaWolfClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site
from phoenixadult.utils.helpers.helpers import pack_cur_id

SITE = find_site('Meana Wolf')
assert SITE is not None

DETAIL_HTML = """<html><body>
  <div class="trailerArea"><h3>Hypno Session</h3></div>
  <div class="trailerContent"><p>A blurb.</p></div>
  <div class="videoContent"><ul>
    <li>RUNTIME: 20 min</li>
    <li>ADDED: March 3, 2021</li>
    <li><a href="/models/alice">Alice</a></li>
    <li><a>Fetish</a><a>POV</a></li>
  </ul></div>
</body></html>"""

ACTOR_HTML = '<html><body><div class="modelBioPic"><img src0_3x="https://cdn.mw.com/alice.jpg"></div></body></html>'


@respx.mock
async def test_search_cards() -> None:
    url = 'https://meanawolf.elxcomplete.com/search.php?query=hypno'
    html = """<html><body>
      <div class="videoBlock">
        <p><a href="/scene/hypno">Hypno Session</a></p>
        <img class="video_placeholder" src="https://cdn.mw.com/poster.jpg">
      </div>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await MeanaWolfClient().search(results, SearchContext(title='hypno', encoded='hypno', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Hypno Session'
    assert results[0].scene_url == 'https://meanawolf.elxcomplete.com/scene/hypno'


@respx.mock
async def test_detail_via_packed_curid() -> None:
    scene_url = 'https://meanawolf.elxcomplete.com/scene/hypno'
    respx.get(scene_url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    respx.get('https://meanawolf.elxcomplete.com/models/alice').mock(return_value=httpx.Response(200, text=ACTOR_HTML))
    cur_id = pack_cur_id([scene_url, 'https://cdn.mw.com/poster.jpg'])
    detail = await MeanaWolfClient().fetch_scene_detail(MeanaWolfClient().decode(cur_id), SITE)
    assert detail is not None
    assert detail.title == 'Hypno Session'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'Meana Wolf'
    assert detail.collections == ['Meana Wolf']
    assert detail.release_date == '2021-03-03'
    assert detail.genres == ['Fetish', 'POV']
    assert [a.name for a in detail.actors] == ['Alice']
    assert detail.actors[0].photo_url == 'https://cdn.mw.com/alice.jpg'
    assert detail.art == ['https://cdn.mw.com/poster.jpg']
