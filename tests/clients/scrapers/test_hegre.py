from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites.hegre import HegreClient
from app.registry import find_site

SITE = find_site('Hegre')
assert SITE is not None

DETAIL_HTML = """<html><head>
  <meta property="og:title" content="Morning Massage">
  <meta name="twitter:image" content="https://p.hegre.com/board-image/x/1600x/cover.jpg">
</head><body>
  <h1>Morning Massage</h1>
  <span class="date">2021-09-09</span>
  <div class="record-description-content record-box-content">A blurb. Runtime 30 min</div>
  <a class="tag">Massage</a><a class="tag">Solo</a>
  <a class="record-model" title="Alice"><img src="https://cdn.hegre.com/240x/alice.jpg"></a>
</body></html>"""


@respx.mock
async def test_search_direct_films() -> None:
    url = 'http://www.hegre.com/films/morning-massage'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    results: list[SearchResult] = []
    await HegreClient().search(results, SearchContext(title='Morning Massage', encoded='Morning%20Massage', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Morning Massage'
    assert results[0].scene_url == url
    assert results[0].score == 100
    assert results[0].release_date == '2021-09-09'


@respx.mock
async def test_detail_fields_genres_actors_images() -> None:
    url = 'http://www.hegre.com/films/morning-massage'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    detail = await HegreClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Morning Massage'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'Hegre'
    assert detail.collections == ['Hegre']
    assert detail.release_date == '2021-09-09'
    assert detail.genres == ['massage', 'solo']
    assert [a.name for a in detail.actors] == ['Alice']
    assert detail.actors[0].photo_url == 'https://cdn.hegre.com/480x/alice.jpg'
    assert detail.directors is not None
    assert detail.directors[0].name == 'Petter Hegre'
    assert detail.raw_image_urls == [
        'https://p.hegre.com/poster-image/x/640x/cover.jpg',
        'https://p.hegre.com/board-image/x/1920x/cover.jpg',
    ]
