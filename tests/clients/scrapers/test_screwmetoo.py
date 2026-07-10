from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext
from app.clients.sites.screwmetoo import ScrewMeTooClient
from app.registry import find_site

SITE = find_site('ScrewMeToo')
assert SITE is not None

DETAIL_HTML = """<html><body>
  <h1>Wild Screw</h1>
  <div><h2>About</h2> A blurb.Read More ...Read Less</div>
  <div class="amp-category">Anal
Hardcore</div>
  <a title="Model Bio - Alice" href="https://screwmetoo.com/models/alice">Alice</a>
  <div class="amp-vis-mobile"><img src="https://cdn.smt.com/p1.jpg"></div>
</body></html>"""

MODEL_HTML = """<html><body>
  <div class="model-contr-colone"><img src="https://cdn.smt.com/alice.jpg"></div>
  <a href="https://screwmetoo.com/content/wild-screw/"><div class="fsdate absolute">2021-08-08</div></a>
</body></html>"""


@respx.mock
async def test_search_cards() -> None:
    url = 'https://screwmetoo.com/?amp=1&s=wild+screw'
    html = """<html><body>
      <div class="fsp bor-r relative"><article>
        <h4>Wild Screw</h4>
        <a href="/content/wild-screw/">x</a>
        <div class="fsdate absolute"><span>2021-08-08</span></div>
      </article></div>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results = await ScrewMeTooClient().search(SearchContext(title='wild screw', encoded='wild+screw', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Wild Screw'
    assert results[0].scene_url == 'https://screwmetoo.com/content/wild-screw/'
    assert results[0].release_date == '2021-08-08'


@respx.mock
async def test_detail_actors_date_genres() -> None:
    url = 'https://screwmetoo.com/content/wild-screw/'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    respx.get('https://screwmetoo.com/models/alice').mock(return_value=httpx.Response(200, text=MODEL_HTML))
    detail = await ScrewMeTooClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Wild Screw'
    assert detail.summary == 'About A blurb.'
    assert detail.studio == 'ScrewMeToo'
    assert detail.release_date == '2021-08-08'
    assert detail.genres == ['Anal', 'Hardcore']
    assert [a.name for a in detail.actors] == ['Alice']
    assert detail.actors[0].photo_url == 'https://cdn.smt.com/alice.jpg'
    assert detail.raw_image_urls == ['https://cdn.smt.com/p1.jpg']
