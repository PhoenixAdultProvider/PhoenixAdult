from __future__ import annotations

import json

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites.sicflics import SicflicsClient
from app.registry import find_site

SITE = find_site('Sicflics')
assert SITE is not None

POPUP_HTML = """<html><body>
  <h4 class="red">SICK TITLE</h4>
  <span title="Date Added">Added: Jan 5, 2024</span>
  <div class="vidwrap"><p>
    <a>#Fisting</a>
    <a>#Extreme</a>
  </p></div>
</body></html>"""


@respx.mock
async def test_search_packs_curid() -> None:
    url = 'https://www.sicflics.com/search/Wild/page1.html'
    html = """<html><body>
      <li class="col-sm-6 col-lg-4">
        <div class="vidthumb"><a class="diagrad"><img src="/thumb.jpg" /></a></div>
        <div class="vidtitle"><p>Wild Scene</p><p>Jan 5, 2024</p></div>
        <a href="#" data-movie="9999">click</a>
        <div class="collapse"><p>Featuring: 'Anna Loma' is wild</p></div>
      </li>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await SicflicsClient().search(results, SearchContext(title='Wild', encoded='Wild', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Wild Scene'
    assert results[0].scene_url == 'https://www.sicflics.com/v6/v6.pop.php?id=9999'
    assert results[0].release_date == '2024-01-05'


@respx.mock
async def test_detail_from_packed_payload() -> None:
    payload = json.dumps(
        {
            'sceneID': '9999',
            'imgURL': 'https://www.sicflics.com/thumb.jpg',
            'description': "Featuring: 'Anna Loma' is wild",
        }
    )
    respx.get('https://www.sicflics.com/v6/v6.pop.php?id=9999').mock(return_value=httpx.Response(200, text=POPUP_HTML))
    detail = await SicflicsClient().fetch_scene_detail(payload, SITE)
    assert detail is not None
    assert detail.title == 'sick title'
    assert detail.summary == "Featuring: 'Anna Loma' is wild"
    assert detail.studio == 'Sicflics'
    assert detail.tagline == 'Sicflics'
    assert detail.collections == ['Sicflics']
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['Fisting', 'Extreme']
    assert [a.name for a in detail.actors] == ['Anna Loma']
    assert detail.art == ['https://www.sicflics.com/thumb.jpg']
