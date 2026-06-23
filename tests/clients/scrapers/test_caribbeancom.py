from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext
from app.clients.sites.caribbeancom import CaribbeancomClient
from app.registry import find_site

SITE = find_site('Caribbeancom')
assert SITE is not None

DETAIL_HTML = """<html><head><title>012345-678</title></head><body>
  <span itemprop="uploadDate">2021/03/09</span>
  <a itemprop="genre">Creampie</a>
  <a itemprop="genre">Big Tits</a>
  <a itemprop="actor"><span itemprop="name">Alice, Bob</span></a>
  <img class="gallery-image" src="/g1.jpg">
  <img class="gallery-image" src="https://cdn.cc.com/g2.jpg">
</body></html>"""


@respx.mock
async def test_search_direct_url_single_result() -> None:
    url = 'https://en.caribbeancom.com/eng/moviepages/012345-678/index.html'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    results = await CaribbeancomClient().search(
        SearchContext(title='012345 678', encoded='012345-678', search_site=SITE.name, site_info=SITE, full_title='012345 678')
    )
    assert len(results) == 1
    assert results[0].title == '012345-678'
    assert results[0].scene_url == url
    assert results[0].score == 100


@respx.mock
async def test_detail_fields_actors_genres_images() -> None:
    url = 'https://en.caribbeancom.com/eng/moviepages/012345-678/index.html'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    detail = await CaribbeancomClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == '012345-678'
    assert detail.studio == 'caribbeancom'
    assert detail.collections == ['caribbeancom']
    assert detail.release_date == '2021-03-09'
    assert detail.genres == ['Creampie', 'Big Tits']
    assert [a.name for a in detail.actors] == ['Alice', 'Bob']
    assert detail.raw_image_urls == [
        'https://en.caribbeancom.com/moviepages/012345-678/images/poster_en.jpg',
        'https://en.caribbeancom.com/g1.jpg',
        'https://cdn.cc.com/g2.jpg',
    ]
