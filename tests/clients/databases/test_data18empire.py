from __future__ import annotations

import httpx
import pytest
import respx

import phoenixadult.clients.aggregators.data18empire as d18e_module
from phoenixadult.clients.aggregators.data18empire import Data18EmpireClient
from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.registry import find_site

SITE = find_site('Data18 Empire')
assert SITE is not None

_COMMON = """
  <div class="synopsis">A grand description.</div>
  <div class="studio"><a>Empire Studios</a></div>
  <div class="release-date"><span>Released:</span> Jan 5, 2024</div>
  <div class="categories"><a>Anal</a><a>Hardcore</a></div>
  <div id="video-container-details">
    <div><section><a><picture><source data-srcset="https://cdn.example/cover.jpg" /></picture></a></section></div>
  </div>
</body></html>"""

MOVIE_PAGE = f"""<html><body>
  <h1 class="description">Big Movie, The</h1>
  <div class="video-performer-container">
    <div class="video-performer">
      <a href="/1/jane-pornstars.html"><img title="Jane Doe" data-bgsrc="https://cdn.example/jane.jpg" /></a>
    </div>
    <div class="performer-name"> Jane Doe </div>
  </div>
  <div class="item-grid item-grid-scene">
    <div class="grid-item"><article class="scene-widget">
      <div class="scene-preview-container">
        <a class="scene-img" href="/scene1"><img src="https://cdn.example/shot1.jpg" /></a>
      </div>
      <p class="scene-performer-names"><a href="/2/mary.html">Mary Roe</a></p>
    </article></div>
  </div>{_COMMON}"""

MOVIE_PAGE_LEGACY_GRID = f"""<html><body>
  <h1 class="description">Big Movie, The</h1>
  <div class="performers"><a>Jane Doe</a></div>
  <div class="item-grid item-grid-scene">
    <div class="grid-item">
      <a class="scene-img" href="/scene1"><img src="https://cdn.example/shot1.jpg" /></a>
      <div class="scene-cast-list"><a>Mary Roe</a></div>
    </div>
  </div>{_COMMON}"""


def _ctx() -> SearchContext:
    return SearchContext(title='', encoded='', search_site=SITE.name, site_info=SITE, scene_id='1234567', full_title='1234567')


@respx.mock
async def test_search_direct_id_split_scene(monkeypatch: pytest.MonkeyPatch, no_web_search: object) -> None:
    monkeypatch.setattr(d18e_module, 'web_search', no_web_search)
    respx.get('https://data18.empirestores.co/1234567').mock(return_value=httpx.Response(200, text=MOVIE_PAGE))
    results: list[SearchResult] = []
    await Data18EmpireClient().search(results, _ctx())
    assert len(results) == 2
    assert results[0].title == 'The Big Movie'
    assert results[0].score == 100
    assert results[1].title == 'The Big Movie [Scene 1]'


@respx.mock
async def test_detail_movie(monkeypatch: pytest.MonkeyPatch, no_web_search: object) -> None:
    monkeypatch.setattr(d18e_module, 'web_search', no_web_search)
    respx.get('https://data18.empirestores.co/1234567').mock(return_value=httpx.Response(200, text=MOVIE_PAGE))
    client = Data18EmpireClient()
    results: list[SearchResult] = []
    await client.search(results, _ctx())
    detail = await client.fetch_scene_detail(client.decode(results[0].cur_id), SITE)
    assert detail is not None
    assert detail.title == 'The Big Movie'
    assert detail.summary == 'A grand description.'
    assert detail.studio == 'Empire Studios'
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['Anal', 'Hardcore']
    assert [(a.name, a.photo_url) for a in detail.actors] == [('Jane Doe', 'https://cdn.example/jane.jpg')]
    assert detail.art == ['https://cdn.example/cover.jpg']


@respx.mock
async def test_detail_split_scene(monkeypatch: pytest.MonkeyPatch, no_web_search: object) -> None:
    monkeypatch.setattr(d18e_module, 'web_search', no_web_search)
    respx.get('https://data18.empirestores.co/1234567').mock(return_value=httpx.Response(200, text=MOVIE_PAGE))
    client = Data18EmpireClient()
    results: list[SearchResult] = []
    await client.search(results, _ctx())
    detail = await client.fetch_scene_detail(client.decode(results[1].cur_id), SITE)
    assert detail is not None
    assert detail.title == 'The Big Movie [Scene 1]'
    assert [a.name for a in detail.actors] == ['Mary Roe']
    assert 'https://cdn.example/shot1.jpg' in detail.art


@respx.mock
async def test_search_sends_age_gate_cookie(monkeypatch: pytest.MonkeyPatch, no_web_search: object) -> None:
    monkeypatch.setattr(d18e_module, 'web_search', no_web_search)
    route = respx.get('https://data18.empirestores.co/1234567').mock(return_value=httpx.Response(200, text=MOVIE_PAGE))
    await Data18EmpireClient().search([], _ctx())
    assert 'ageConfirmed=true' in route.calls[0].request.headers['Cookie']


@respx.mock
async def test_search_direct_id_matches_numeric_path_segment(monkeypatch: pytest.MonkeyPatch, no_web_search: object) -> None:
    monkeypatch.setattr(d18e_module, 'web_search', no_web_search)
    url = 'https://data18.empirestores.co/1234567/big-movie-porn-movies.html'
    respx.get('https://data18.empirestores.co/1234567').mock(return_value=httpx.Response(301, headers={'Location': url}))
    respx.get(url).mock(return_value=httpx.Response(200, text=MOVIE_PAGE))
    results: list[SearchResult] = []
    await Data18EmpireClient().search(results, _ctx())
    assert results[0].score == 100


@respx.mock
async def test_detail_legacy_grid_shape_still_parses(monkeypatch: pytest.MonkeyPatch, no_web_search: object) -> None:
    monkeypatch.setattr(d18e_module, 'web_search', no_web_search)
    respx.get('https://data18.empirestores.co/1234567').mock(return_value=httpx.Response(200, text=MOVIE_PAGE_LEGACY_GRID))
    client = Data18EmpireClient()
    results: list[SearchResult] = []
    await client.search(results, _ctx())
    assert len(results) == 2
    movie = await client.fetch_scene_detail(client.decode(results[0].cur_id), SITE)
    assert movie is not None and [a.name for a in movie.actors] == ['Jane Doe']
    scene = await client.fetch_scene_detail(client.decode(results[1].cur_id), SITE)
    assert scene is not None and [a.name for a in scene.actors] == ['Mary Roe']
    assert 'https://cdn.example/shot1.jpg' in scene.art


def test_is_movie_url_accepts_real_empire_urls() -> None:
    accept = [
        'https://data18.empirestores.co/1872061/yoga-freaks-porn-movies.html',
        'https://data18.empirestores.co/movies/1872061',
    ]
    reject = [
        'https://data18.empirestores.co/474349/some-scene-streaming-scene-video.html',
        'https://data18.empirestores.co/664699/abella-danger-pornstars.html',
        'https://data18.empirestores.co/Search?q=yoga',
    ]
    assert all(d18e_module._is_movie_url(u) for u in accept)
    assert not any(d18e_module._is_movie_url(u) for u in reject)


@respx.mock
async def test_scene_id_scores_via_id_distance(monkeypatch: pytest.MonkeyPatch, no_web_search: object) -> None:
    monkeypatch.setattr(d18e_module, 'web_search', no_web_search)
    respx.get('https://data18.empirestores.co/1234567').mock(return_value=httpx.Response(200, text=MOVIE_PAGE))
    results: list[SearchResult] = []
    await Data18EmpireClient().search(results, _ctx())
    assert results and all(r.score == 100 for r in results)


@respx.mock
async def test_without_scene_id_scoring_falls_back_to_title(monkeypatch: pytest.MonkeyPatch, no_web_search: object) -> None:
    monkeypatch.setattr(d18e_module, 'web_search', no_web_search)
    search_page = '<html><body><a class="boxcover" href="/1234567/big-movie-porn-movies.html"></a></body></html>'
    respx.get(url__regex=r'.*/Search\?q=.*').mock(return_value=httpx.Response(200, text=search_page))
    respx.get('https://data18.empirestores.co/1234567/big-movie-porn-movies.html').mock(return_value=httpx.Response(200, text=MOVIE_PAGE))
    ctx = SearchContext(title='The Big Movie', encoded='The+Big+Movie', search_site=SITE.name, site_info=SITE)
    results: list[SearchResult] = []
    await Data18EmpireClient().search(results, ctx)
    assert results and results[0].score == 100


def test_rotate_article_handles_mid_string_the() -> None:
    assert d18e_module._rotate_article('Movie, The (Disc 2)') == 'The Movie (Disc 2)'
    assert d18e_module._rotate_article('Big Movie, The') == 'The Big Movie'
    assert d18e_module._rotate_article('No Article Here') == 'No Article Here'
