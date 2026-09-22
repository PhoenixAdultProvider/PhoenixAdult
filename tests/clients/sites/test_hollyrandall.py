from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.sites.hollyrandall import HollyRandallClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site
from phoenixadult.utils.helpers.ids import b64url_encode, pack_cur_id
from tests.support import served_collections

SITE = find_site('Holly Randall')
assert SITE is not None

DETAIL_HTML = """<html><body>
  <ul class="tags"><li><a>Solo</a></li><li><a>Glamour</a></li></ul>
  <div class="info"><p>line0
line1
line2
Featuring: Alice, Bob</p></div>
  <img class="x update_thumb" src0_3x="https://cdn.hr.com/t1.jpg">
  <img class="update_thumb" src0_3x="/t2.jpg">
</body></html>"""


@respx.mock
async def test_search_parses_cards() -> None:
    url = 'https://hollyrandall.com/search.php?query=glam'
    html = """<html><body>
      <div class="item-video">
        <div class="item-thumb"><a href="/scene/glam-1" title="Glam Shoot">x</a></div>
        <div class="timeDate">Posted | 2021-06-06</div>
      </div>
      <div class="item-video">
        <div class="item-thumb"><a href="https://join.hollyrandall.com/promo" title="Join Now">x</a></div>
      </div>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await HollyRandallClient().search(results, SearchContext(title='glam', encoded='glam', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Glam Shoot'
    assert results[0].scene_url == 'https://hollyrandall.com/scene/glam-1'
    assert results[0].release_date == '2021-06-06'


@respx.mock
async def test_detail_via_packed_curid() -> None:
    scene_url = 'https://hollyrandall.com/scene/glam-1'
    respx.get(scene_url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    cur_id = pack_cur_id([scene_url, f'2021-06-06|{b64url_encode("Glam Shoot")}'])
    detail = await HollyRandallClient().fetch_scene_detail(HollyRandallClient().decode(cur_id), SITE)
    assert detail is not None
    assert detail.title == 'Glam Shoot'
    assert detail.studio == 'Holly Randall Productions'
    assert served_collections(detail) == ['Holly Randall']
    assert detail.release_date == '2021-06-06'
    assert detail.genres == ['Solo', 'Glamour']
    assert [a.name for a in detail.actors] == ['Alice', 'Bob']
    assert detail.art == ['https://cdn.hr.com/t1.jpg', 'https://hollyrandall.com/t2.jpg']
