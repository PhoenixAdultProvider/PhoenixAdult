from __future__ import annotations

import json

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites.jesseloadsmonsterfacials import JesseLoadsMonsterFacialsClient
from app.registry import find_site
from app.utils.helpers.helpers import pack_cur_id

SITE = find_site('Jesse Loads Monster Facials')
assert SITE is not None

TOUR_HTML = """<html><body>
  <span class="bppindex"><select><option value="1">1</option></select></span>
  <b>Update: 06/06/2021</b>
  <table width="880">
    <tr><td height="105">Aaliyah does her thing here.</td></tr>
    <img src="/tour/poster.jpg" width="400">
    <img src="/fft/x_weaaliyahlove.jpg">
  </table>
</body></html>"""


@respx.mock
async def test_search_walks_tour() -> None:
    respx.get('http://jesseloadsmonsterfacials.com/visitors/tour_01.html').mock(return_value=httpx.Response(200, text=TOUR_HTML))
    results: list[SearchResult] = []
    await JesseLoadsMonsterFacialsClient().search(results, SearchContext(title='aaliyah', encoded='aaliyah', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Aaliyah Love'
    assert results[0].release_date == '2021-06-06'


async def test_detail_from_curid() -> None:
    detail_data = {
        'poster': 'http://jesseloadsmonsterfacials.com/tour/poster.jpg',
        'releaseDate': '2021-06-06',
        'actors': ['Aaliyah Love'],
        'summary': 'A blurb.',
    }
    cur_id = pack_cur_id([json.dumps(detail_data)])
    detail = await JesseLoadsMonsterFacialsClient().fetch_scene_detail(JesseLoadsMonsterFacialsClient().decode(cur_id), SITE)
    assert detail is not None
    assert detail.title == 'Aaliyah Love from JesseLoadsMonsterFacials.com'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'Jesse Loads Monster Facials'
    assert detail.collections == ['Jesse Loads Monster Facials']
    assert detail.release_date == '2021-06-06'
    assert detail.genres == ['Facial']
    assert [a.name for a in detail.actors] == ['Aaliyah Love']
    assert detail.art == ['http://jesseloadsmonsterfacials.com/tour/poster.jpg']
