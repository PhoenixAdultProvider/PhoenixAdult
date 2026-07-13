from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites.clubfilly import ClubFillyClient
from app.registry import find_site

SITE = find_site('ClubFilly')
assert SITE is not None

DETAIL_HTML = """<html><body>
  <div class="fltWrap"><h1><span>Filly Fun</span></h1></div>
  <div class="fltRight">Release Date : 2020-08-15</div>
  <p class="description">Description: A blurb.</p>
  <p class="starring">Starring: Alice, Bob, Carol</p>
  <ul id="lstSceneFocus">
    <li><img src="https://cdn.cf.com/s1.jpg"></li>
    <li><img src="/s2.jpg"></li>
  </ul>
</body></html>"""


@respx.mock
async def test_search_direct_url_single_result() -> None:
    url = 'https://clubfilly.com/scenefocus.php?vnum=V12345'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    results: list[SearchResult] = []
    await ClubFillyClient().search(results, SearchContext(title='12345', encoded='12345', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Filly Fun'
    assert results[0].scene_url == url
    assert results[0].score == 100


@respx.mock
async def test_detail_fields_actors_genres_images() -> None:
    url = 'https://clubfilly.com/scenefocus.php?vnum=V12345'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    detail = await ClubFillyClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Filly Fun'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'ClubFilly'
    assert detail.tagline == 'ClubFilly'
    assert detail.collections == ['ClubFilly']
    assert detail.release_date == '2020-08-15'
    assert [a.name for a in detail.actors] == ['Alice', 'Bob', 'Carol']
    assert detail.genres == ['Lesbian', 'Threesome']
    assert detail.raw_image_urls == ['https://cdn.cf.com/s1.jpg', 'https://clubfilly.com/s2.jpg']
