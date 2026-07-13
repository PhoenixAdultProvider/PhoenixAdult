from __future__ import annotations

from urllib.parse import quote

import httpx
import pytest
import respx

import app.clients.sites.adultempire as ae_module
from app.clients.base import SearchContext, SearchResult
from app.clients.sites.adultempire import AdultEmpireClient
from app.registry import find_site

SITE = find_site('Adult Empire')
assert SITE is not None

MOVIE_PAGE = """<html><body>
  <h1>Big Compilation</h1>
  <div class="container"><h2>Synopsis</h2><p>A great compilation.</p></div>
  <ul>
    <li>Studio: <a>Empire Studios</a></li>
    <li>Released: Jan 5 2024</li>
    <li><a label="Category">Anal</a></li>
  </ul>
  <h2><a label="Series">Compilation Vol "Best Of The Best (2024)"</a></h2>
  <div>Starring <a href="/12345/jane-doe/porn-videos/" label="Performers - detail">Jane Doe</a><img title="Jane Doe" src="https://cdn.example/jane.jpg" /></div>
  <div class="boxcover-container">
    <a href="https://cdn.example/cover-big.jpg"><img src="https://cdn.example/cover.jpg" /></a>
  </div>
  <div>
    <a name="cast"></a>
    <ul>
      <li><strong>Director:</strong> <a>Mike Boss</a></li>
      <li><strong>Producer:</strong> John Smith</li>
    </ul>
  </div>
  <div class="row">
    <div class="row"><a rel="scenescreenshots"></a></div>
    <div class="row"><a href="https://cdn.example/shot-1.jpg"></a></div>
    <div class="row"><a href="https://cdn.example/shot-2.jpg"></a></div>
  </div>
  <div class="row"><h3><a>Scene One</a></h3><div><a>Mary Roe</a></div></div>
</body></html>"""


def _mock_age_gate() -> None:
    respx.get('https://www.adultempire.com/').mock(return_value=httpx.Response(200, text=''))
    respx.get(url__startswith='https://www.adultempire.com/Account/AgeConfirmation').mock(
        return_value=httpx.Response(200, headers={'set-cookie': 'ageConfirmed=true; path=/'}, text='')
    )


def _ctx(scene_id: str | None = None, title: str = '') -> SearchContext:
    return SearchContext(title=title, encoded=quote(title), search_site=SITE.name, site_info=SITE, scene_id=scene_id, full_title=scene_id or title)


@respx.mock
async def test_requests_carry_age_cookie(no_web_search: object) -> None:
    _mock_age_gate()
    seen: dict[str, str | None] = {}

    def cap(request: httpx.Request) -> httpx.Response:
        seen['cookie'] = request.headers.get('cookie')
        return httpx.Response(200, text=MOVIE_PAGE)

    respx.get('https://www.adultempire.com/1234567').mock(side_effect=cap)
    await AdultEmpireClient().search([], _ctx(scene_id='1234567'))
    assert seen.get('cookie') is not None
    assert 'ageConfirmed=true' in (seen['cookie'] or '')


@respx.mock
async def test_search_direct_id_with_split_scene(no_web_search: object) -> None:
    _mock_age_gate()
    respx.get('https://www.adultempire.com/1234567').mock(return_value=httpx.Response(200, text=MOVIE_PAGE))
    results: list[SearchResult] = []
    await AdultEmpireClient().search(results, _ctx(scene_id='1234567'))
    assert len(results) == 2
    assert results[0].title == 'Big Compilation [Empire Studios]'
    assert results[0].score == 100
    assert results[1].title == 'Big Compilation / #1 Scene One[Mary Roe][Empire Studios]'


@respx.mock
async def test_search_onsite_vol_scoring(monkeypatch: pytest.MonkeyPatch, no_web_search: object) -> None:
    _mock_age_gate()
    monkeypatch.setattr(ae_module, 'web_search', no_web_search)
    vol_movie = '<html><body><h1>Anal Compilation Vol. 3</h1><ul><li>Studio: <a>Empire Studios</a></li></ul></body></html>'
    search_results = (
        '<html><body><div class="product-details__item-title"><a href="/9999-anal-compilation-blu-ray.html">Anal Compilation</a></div></body></html>'
    )
    respx.get('https://www.adultempire.com/allsearch/search?q=Anal+Vol+3').mock(return_value=httpx.Response(200, text=search_results))
    respx.get('https://www.adultempire.com/9999-anal-compilation-blu-ray.html').mock(return_value=httpx.Response(200, text=vol_movie))
    results: list[SearchResult] = []
    await AdultEmpireClient().search(results, _ctx(title='Anal Vol 3'))
    assert len(results) >= 1
    assert results[0].title == '[Vol. 3] Anal Compilation [Empire Studios] [Blu-Ray]'
    assert 0 < (results[0].score or 0) <= 100


@respx.mock
async def test_search_skips_interview_siblings() -> None:
    _mock_age_gate()
    interview_page = """<html><body>
      <h1>Cast Roster</h1>
      <ul><li>Studio: <a>Empire Studios</a></li></ul>
      <div>Starring
        <ul class="list-unstyled">
          <li><a href="/1/samantha-saint/porn-videos/" label="Performers - detail" class="PerformerName"> Samantha Saint </a></li>
          <li><a href="/2/julia-ann/porn-videos/" label="Performers - detail" class="PerformerName"> Julia Ann </a>
              <small> - <a href="/interviews/2" label="Performers - Interview - detail">Interview</a></small></li>
          <li><a href="/3/evan-stone/porn-videos/" label="Performers - detail" class="PerformerName"> Evan Stone </a>
              - <a href="/interviews/3" label="Performers - Interview - detail">Interview</a></li>
          <li><a href="/d/1" label="Director - details"> Axel Braun</a><small>Director</small></li>
        </ul>
      </div>
    </body></html>"""
    respx.get('https://www.adultempire.com/8888888').mock(return_value=httpx.Response(200, text=interview_page))
    client = AdultEmpireClient()
    results: list[SearchResult] = []
    await client.search(results, _ctx(scene_id='8888888'))
    detail = await client.fetch_scene_detail(client.decode(results[0].cur_id), SITE)
    assert detail is not None
    assert [a.name for a in detail.actors] == ['Samantha Saint', 'Julia Ann', 'Evan Stone']


@respx.mock
async def test_search_strips_sale_banner_h1() -> None:
    _mock_age_gate()
    sale_page = """<html><body>
      <div class="col-sm-6 col-md-7">
        <h1 class="movie-page__heading__title"> Un-Pure Evil
          <span class="movie-page__heading__title__sale-indicator sale"> - On Sale! <a href="/s/x.html" label="Performers - detail">Sale</a></span>
        </h1>
      </div>
      <ul><li>Studio: <a>Evil Angel</a></li></ul>
    </body></html>"""
    respx.get('https://www.adultempire.com/7654321').mock(return_value=httpx.Response(200, text=sale_page))
    results: list[SearchResult] = []
    await AdultEmpireClient().search(results, _ctx(scene_id='7654321'))
    assert results[0].title == 'Un-Pure Evil [Evil Angel]'


@respx.mock
async def test_detail_movie() -> None:
    _mock_age_gate()
    respx.get('https://www.adultempire.com/1234567').mock(return_value=httpx.Response(200, text=MOVIE_PAGE))
    client = AdultEmpireClient()
    results: list[SearchResult] = []
    await client.search(results, _ctx(scene_id='1234567'))
    detail = await client.fetch_scene_detail(client.decode(results[0].cur_id), SITE)
    assert detail is not None
    assert detail.title == 'Big Compilation'
    assert detail.summary == 'A great compilation.'
    assert detail.studio == 'Empire Studios'
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['Anal']
    assert [(a.name, a.photo_url) for a in detail.actors] == [('Jane Doe', 'https://cdn.example/jane.jpg')]
    assert detail.tagline == 'Best Of The Best'
    assert detail.collections == ['Empire Studios', 'Best Of The Best']
    assert detail.directors is not None and [d.name for d in detail.directors] == ['Mike Boss']
    assert detail.producers is not None and [p.name for p in detail.producers] == ['John Smith']
    assert detail.art == [
        'https://cdn.example/cover.jpg',
        'https://cdn.example/cover-big.jpg',
        'https://cdn.example/shot-1.jpg',
        'https://cdn.example/shot-2.jpg',
    ]


@respx.mock
async def test_detail_split_scene() -> None:
    _mock_age_gate()
    respx.get('https://www.adultempire.com/1234567').mock(return_value=httpx.Response(200, text=MOVIE_PAGE))
    client = AdultEmpireClient()
    results: list[SearchResult] = []
    await client.search(results, _ctx(scene_id='1234567'))
    detail = await client.fetch_scene_detail(client.decode(results[1].cur_id), SITE)
    assert detail is not None
    assert detail.title == 'Big Compilation [Scene 1]'
    assert [a.name for a in detail.actors] == ['Mary Roe']
