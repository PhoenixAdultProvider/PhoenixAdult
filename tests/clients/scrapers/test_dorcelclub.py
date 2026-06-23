from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext
from app.clients.sites.dorcelclub import DorcelClubClient
from app.registry import find_site

SITE = find_site('Dorcel Club')
assert SITE is not None

SEARCH_HTML = """<html><body>
  <div class="scenes list"><div class="items">
    <div class="scene thumbnail ">
      <div class="textual"><a>Scene One</a></div>
      <a class="title" href="/en/porn-scene/1/scene-one"></a>
    </div>
  </div></div>
  <div class="movies list"><div class="items">
    <a class="movie thumbnail" href="/en/porn-movie/9/big-movie"><h2>Big Movie</h2></a>
  </div></div>
</body></html>"""

MOVIE_HTML = """<html><body>
  <div class="scenes"><div class="list">
    <div class="scene thumbnail ">
      <div class="textual"><a>Movie Scene A</a></div>
      <a class="title" href="/en/porn-scene/2/movie-scene-a"></a>
    </div>
  </div></div>
</body></html>"""

SCENE_DETAIL_HTML = """<html><body>
  <h1>Scene One</h1>
  <span class="full">A blurb.</span>
  <span class="publish_date">2021-11-11</span>
  <span class="movie"><a>Big Movie</a></span>
  <span class="director">Director : Jane Doe</span>
  <div class="actress"><a>Alice</a></div>
  <div class="actress"><a>Bob</a></div>
  <div class="actress"><a>Carol</a></div>
  <div class="photos"><source data-srcset="https://cdn.dc.com/a_b_1536.jpg 2x"></source></div>
</body></html>"""


@respx.mock
async def test_search_scenes_and_movie_subscenes() -> None:
    search_url = 'https://www.dorcelclub.com/en/search?s=big'
    movie_url = 'https://www.dorcelclub.com/en/porn-movie/9/big-movie'
    respx.get(search_url).mock(return_value=httpx.Response(200, text=SEARCH_HTML))
    respx.get(movie_url).mock(return_value=httpx.Response(200, text=MOVIE_HTML))
    results = await DorcelClubClient().search(SearchContext(title='big', encoded='big', search_site=SITE.name, site_info=SITE))
    titles = [r.title for r in results]
    assert titles == ['Scene One', 'Big Movie - Full Movie', 'Movie Scene A']
    assert results[1].scene_url == movie_url


@respx.mock
async def test_detail_scene_path() -> None:
    url = 'https://www.dorcelclub.com/en/porn-scene/1/scene-one'
    respx.get(url).mock(return_value=httpx.Response(200, text=SCENE_DETAIL_HTML))
    detail = await DorcelClubClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Scene One'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'Marc Dorcel'
    assert detail.collections == ['Dorcel Club', 'Big Movie']
    assert detail.release_date == '2021-11-11'
    assert detail.genres == ['French porn', 'Blockbuster Movie', 'Threesome']
    assert [a.name for a in detail.actors] == ['Alice', 'Bob', 'Carol']
    assert detail.directors is not None
    assert detail.directors[0].name == 'Jane Doe'
    # srcset cleaned: comma-split last, density stripped, '_1536' trash removed
    assert detail.raw_image_urls == ['https://cdn.dc.com/a_b.jpg']
