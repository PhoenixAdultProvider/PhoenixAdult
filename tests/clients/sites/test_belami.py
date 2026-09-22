from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.sites.belami import BelAmiClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site
from tests.support import served_collections

SITE = find_site('Bel Ami Online')
assert SITE is not None

DETAIL_HTML = """<html><body>
  <div class="video_detail">
    <span id="ContentPlaceHolder1_LabelTitle">Summer Boys</span>
    <span id="ContentPlaceHolder1_LabelReleased">06/16/2021</span>
    <div class="bottom"><p>Upsell blurb.</p><p>A real blurb.</p></div>
    <span id="ContentPlaceHolder1_LabelTags"><a>Twink</a><a>Outdoor</a></span>
    <div class="right"><div class="actors_list">
      <div class="actor"><a>Alice<img src="https://cdn.bel.com/a.jpg"></a></div>
      <div class="actor"><a>Bob<img src="https://cdn.bel.com/b.jpg"></a></div>
      <div class="actor"><a>Carol<img src="https://cdn.bel.com/c.jpg"></a></div>
    </div></div>
  </div>
</body></html>"""


@respx.mock
async def test_search_direct_url_single_result() -> None:
    url = 'https://newtour.belamionline.com/playvideo.aspx?VideoID=987'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    results: list[SearchResult] = []
    await BelAmiClient().search(results, SearchContext(title='987 summer boys', encoded='987', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Summer Boys'
    assert results[0].scene_url == url
    assert results[0].score == 100


@respx.mock
async def test_detail_fields_actors_genres_poster() -> None:
    url = 'https://newtour.belamionline.com/playvideo.aspx?VideoID=987'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    detail = await BelAmiClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Summer Boys'
    assert detail.summary == 'A real blurb.'
    assert detail.studio == 'Bel Ami Online'
    assert served_collections(detail) == ['Bel Ami Online']
    assert detail.release_date == '2021-06-16'
    assert detail.genres == ['Twink', 'Outdoor', 'Threesome']
    assert [a.name for a in detail.actors] == ['Alice', 'Bob', 'Carol']
    assert detail.actors[0].photo_url == 'https://cdn.bel.com/a.jpg'
    assert detail.art == ['https://freecdn.belamionline.com/Data/Contents/Content_987/Thumbnail8.jpg']
