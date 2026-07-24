from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.sites.kin8tengoku import Kin8tengokuClient
from phoenixadult.registry import find_site

SITE = find_site('Kin8tengoku')
assert SITE is not None

DETAIL_HTML = """<html><body>
  <p class="sub_title_vip">Blonde Beauty / Some JP text</p>
  <table>
    <tr><td>Date</td><td class="movie_table_td2">2021-05-05</td></tr>
    <tr><td>Category</td><td><a>Blonde</a><a>Creampie</a></td></tr>
    <tr><td>Model</td><td><a>Alice</a></td></tr>
  </table>
</body></html>"""

SEARCH_URL = 'https://en.kin8tengoku.com/gateway/entry.phpgw?en=1&provider_id=4034&action=list&q=blonde'


@respx.mock
async def test_search_direct_by_sceneid() -> None:
    direct = 'https://en.kin8tengoku.com/moviepages/3210/index.html'
    respx.get(direct).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, text='<html><body></body></html>'))
    results: list[SearchResult] = []
    await Kin8tengokuClient().search(results, SearchContext(title='blonde', encoded='blonde', search_site=SITE.name, site_info=SITE, scene_id='3210'))
    assert any(r.scene_url == direct for r in results)
    hit = next(r for r in results if r.scene_url == direct)
    assert hit.title == 'Blonde Beauty'
    assert hit.score == 100
    assert hit.release_date == '2021-05-05'


@respx.mock
async def test_detail_table_fields() -> None:
    url = 'https://en.kin8tengoku.com/moviepages/3210/index.html'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    detail = await Kin8tengokuClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Blonde Beauty'
    assert detail.studio == 'Kin8tengoku'
    assert detail.collections == ['Kin8tengoku']
    assert detail.release_date == '2021-05-05'
    assert detail.genres == ['Blonde', 'Creampie']
    assert [a.name for a in detail.actors] == ['Alice']
