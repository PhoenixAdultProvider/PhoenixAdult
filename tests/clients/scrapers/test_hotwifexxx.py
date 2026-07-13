from __future__ import annotations

import httpx
import pytest
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites import hotwifexxx as hwxxx_module
from app.clients.sites.hotwifexxx import HotwifeXXXClient
from app.registry import find_site

SITE = find_site('HotwifeXXX')
assert SITE is not None

SCENE_URL = 'http://www.hotwifexxx.com/tour_hwxxx/updates/wild-wife.html'

DETAIL_HTML = """<html><body>
  <div class="trailerInfo">
    <h2>Wild Wife</h2>
    <div class="released2 trailerStarr">06/06/2021, Starring: Alice</div>
  </div>
  <div class="dvdDescription"><p>Description: A blurb.</p></div>
  <div class="trailerMInfo"><span class="tour_update_models">
    <a href="/models/alice">Alice</a><a href="/models/bob">Bob</a><a href="/models/carol">Carol</a>
  </span></div>
  <span id="trailer_thumb"><img src="https://cdn.hw.com/t1.jpg"></span>
</body></html>"""


@respx.mock
async def test_search_web_filtered(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _web(*_a: object, **_k: object) -> list[str]:
        return [SCENE_URL, 'http://www.hotwifexxx.com/other/page.html']

    monkeypatch.setattr(hwxxx_module, 'web_search', _web)
    respx.get(SCENE_URL).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    results: list[SearchResult] = []
    await HotwifeXXXClient().search(results, SearchContext(title='wild wife', encoded='wild-wife', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Wild Wife'
    assert results[0].scene_url == SCENE_URL
    assert results[0].release_date == '2021-06-06'


@respx.mock
async def test_detail_summary_genres_actors_images() -> None:
    respx.get(SCENE_URL).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    actor_html = '<html><body><div class="modelBioPic"><img src0_3x="https://cdn.hw.com/alice.jpg"></div></body></html>'
    for slug in ('alice', 'bob', 'carol'):
        body = actor_html.replace('alice', slug)
        respx.get(f'http://www.hotwifexxx.com/models/{slug}').mock(return_value=httpx.Response(200, text=body))
    detail = await HotwifeXXXClient().fetch_scene_detail(SCENE_URL, SITE)
    assert detail is not None
    assert detail.title == 'Wild Wife'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'HotwifeXXX'
    assert detail.collections == ['HotwifeXXX']
    assert detail.release_date == '2021-06-06'
    assert detail.genres == ['Threesome']
    assert [a.name for a in detail.actors] == ['Alice', 'Bob', 'Carol']
    assert detail.actors[0].photo_url == 'https://cdn.hw.com/alice.jpg'
    assert detail.art == ['https://cdn.hw.com/t1.jpg']
