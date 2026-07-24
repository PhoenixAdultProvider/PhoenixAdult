from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.sites.dorcelvision import DorcelVisionClient
from phoenixadult.registry import find_site

SITE = find_site('Dorcel Vision')
assert SITE is not None

DETAIL_HTML = """<html><head>
  <meta name="twitter:description" content="A blurb.">
</head><body>
  <h1>Vision Movie</h1>
  <div class="entries">
    <p><strong>Studio:</strong> <a>Wild Studio</a></p>
    <p><strong>Production year:</strong> 2019 </p>
  </div>
  <div class="casting"><div class="slider-xl">
    <div class="col-xs-2"><a><strong>Alice</strong></a><img data-src="/img/alice.jpg"></div>
  </div></div>
  <div class="covers"><a class="cover" href="/blur9/cover.jpg">x</a></div>
  <div class="screenshots"><div class="slider-xl"><div class="col-xs-2"><a href="https://cdn.dv.com/s1.jpg">x</a></div></div></div>
</body></html>"""


@respx.mock
async def test_search_movie_cards() -> None:
    url = 'https://www.dorcelvision.com/en/search?type=4&keyword=vision'
    html = """<html><body>
      <a class="movies" href="/en/movies/9/vision-movie"><img alt="Vision Movie"></a>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await DorcelVisionClient().search(results, SearchContext(title='vision', encoded='vision', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Vision Movie'
    assert results[0].scene_url == 'https://www.dorcelvision.com/en/movies/9/vision-movie'


@respx.mock
async def test_detail_studio_override_year_actors_images() -> None:
    url = 'https://www.dorcelvision.com/en/movies/9/vision-movie'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    detail = await DorcelVisionClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Vision Movie'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'Wild Studio'
    assert detail.collections == ['Dorcel Vision', 'Wild Studio']
    assert detail.release_date == '2019-01-01'
    assert len(detail.actors) == 1
    assert detail.actors[0].name == 'Alice'
    assert detail.actors[0].photo_url == 'https://www.dorcelvision.com/img/alice.jpg'
    assert detail.art == ['https://www.dorcelvision.com/cover.jpg', 'https://cdn.dv.com/s1.jpg']
