from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext
from app.clients.sites.sinslife import SinsLifeClient
from app.registry import find_site

SITE = find_site('SinsLife')
assert SITE is not None

# Deep positional layout mirrors the legacy //div[4]/... XPaths.
DETAIL_HTML = """<html><body>
  <div class="section"><h1>Wild Night</h1></div>
  <div></div>
  <div></div>
  <div>
    <div>
      <div></div>
      <div>
        <div>
          <div>
            <div>
              <div></div>
              <div><div><div><img src="//cdn.sl.com/poster.jpg"></div></div></div>
            </div>
            <div>
              <div><div><div>Release Date: January 5, 2024</div></div></div>
              <div><p>A wild blurb.</p></div>
              <div><ul><li>Kissa Sins</li><li>Johnny Sins</li><li>Third Star</li></ul></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</body></html>"""


@respx.mock
async def test_search_cards() -> None:
    url = 'https://sinslife.com/tour/search.php?query=wild'
    html = """<html><body>
      <div></div><div></div><div></div>
      <div><div>
        <div></div><div></div>
        <div><div><div>
          <a title="Wild Night" href="/tour/scene/wild">link</a>
        </div></div></div>
      </div></div>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results = await SinsLifeClient().search(SearchContext(title='wild', encoded='wild', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Wild Night'
    assert results[0].scene_url == 'https://sinslife.com/tour/scene/wild'


@respx.mock
async def test_detail() -> None:
    url = 'https://sinslife.com/tour/scene/wild'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    detail = await SinsLifeClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Wild Night'
    assert detail.summary == 'A wild blurb.'
    assert detail.studio == 'SinsLife'
    assert detail.tagline == 'SinsLife'
    assert detail.collections == ['SinsLife']
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['Threesome']
    assert [a.name for a in detail.actors] == ['Kissa Sins', 'Johnny Sins', 'Third Star']
    assert detail.raw_image_urls == ['https://cdn.sl.com/poster.jpg']
