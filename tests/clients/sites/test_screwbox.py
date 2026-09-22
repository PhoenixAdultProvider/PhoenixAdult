from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.sites.screwbox import ScrewboxClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site

SITE = find_site('Screwbox')
assert SITE is not None

DETAIL_HTML = """<html><body>
  <div class="item-details-right"><h1>Box Scene</h1></div>
  <p class="shorter">A blurb.</p>
  <ul class="more-info">
    <li>Cast: <a href="//screwbox.com/models/alice">alice</a></li>
    <li>RELEASE DATE: 2021-06-06</li>
    <li>Categories: <a>anal</a><a>pov</a></li>
  </ul>
  <div class="fakeplayer"><img src0_1x="https://cdn.sb.com/poster.jpg"></div>
</body></html>"""

ACTOR_HTML = '<html><body><img class="model_bio_thumb" src0_1x="https://cdn.sb.com/alice.jpg"></body></html>'


@respx.mock
async def test_search_cards() -> None:
    url = 'https://screwbox.com/search.php?query=box'
    html = """<html><body>
      <div class="item"><h4><a href="//screwbox.com/scene/box">Box Scene</a></h4></div>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await ScrewboxClient().search(results, SearchContext(title='box', encoded='box', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Box Scene'
    assert results[0].scene_url == 'https://screwbox.com/scene/box'


@respx.mock
async def test_detail_fields_actors_images() -> None:
    url = 'https://screwbox.com/scene/box'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    respx.get('https://screwbox.com/models/alice').mock(return_value=httpx.Response(200, text=ACTOR_HTML))
    detail = await ScrewboxClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Box Scene'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'Screwbox'
    assert detail.release_date == '2021-06-06'
    assert detail.genres == ['Anal', 'POV']
    assert [a.name for a in detail.actors] == ['Alice']
    assert detail.actors[0].photo_url == 'https://cdn.sb.com/alice.jpg'
    assert detail.art == ['https://cdn.sb.com/poster.jpg']
