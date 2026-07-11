from __future__ import annotations

from urllib.parse import quote

import httpx
import pytest
import respx

import app.clients.aggregators.data18movies as d18m_module
from app.clients.aggregators.data18movies import Data18MoviesClient
from app.clients.base import SearchContext
from app.registry import find_site

SITE = find_site('Data18 Movies')
assert SITE is not None

SEARCH_PAGE = """<html><body>
  pages: 1
  <a href="https://www.data18.com/movies/12345-big-movie">
    <p class="gen12 bold">Big Movie</p>
    <span class="gen11"><b>#1</b> January, 2024&nbsp;<i>ZZ Series</i></span>
  </a>
</body></html>"""

_HEAD = '<h1><a href="/movies/12345">Big Movie</a></h1>'
_BODY = """
  <div class="gen12"><div>Description --- A grand description. Studio: Empire Studios</div></div>
  <p><b>Categories</b>: <a>Anal</a><a>Hardcore</a></p>
  <h3>Pornstars / Cast of Big Movie</h3>
  <div><a href="/name/jane"><img alt="Jane Doe" data-src="https://cdn.example/jane.jpg" /></a></div>
  <p><b>Director</b>: Joe Helmer</p>
  <a id="enlargecover" data-featherlight="https://cdn.example/cover.jpg"></a>
</body></html>"""

MOVIE_PAGE = f"""<html><body>{_HEAD}
  <p><b>Network</b>: <b><a href="/studios/empire">Empire Studios</a></b>
     <span class="gen11">- 875 Movies <span><b>R</b> Nav</span></span> |
     Site: <a href="/studios/empire/zz-series">ZZ Series</a></p>
  <span>Prod. Year: 2024 - Release date: January, 2024</span>{_BODY}"""

MOVIE_PAGE_DATETIME = f"""<html><body>{_HEAD}
  <p><b>Studio</b>: <b><a href="/studios/empire">Empire Studios</a></b></p>
  <time datetime="2024-01-05"></time>{_BODY}"""

MOVIE_PAGE_REPTYLE = f"""<html><body>{_HEAD}
  <p><b>Network</b>: <b><a href="/studios/teamskeet">TeamSkeet - Reptyle</a></b>
     <span class="gen11">- 1 Movies</span> |
     Site: <a href="/studios/teamskeet">TeamSkeet - Reptyle</a></p>
  <span>Release date: January, 2024</span>{_BODY}"""


@respx.mock
async def test_search_candidates(monkeypatch: pytest.MonkeyPatch, no_web_search: object) -> None:
    monkeypatch.setattr(d18m_module, 'web_search', no_web_search)
    q = quote('Big Movie')
    respx.get(f'https://www.data18.com/sys/live.php?index=&key={q}&key2={q}&next=1&page=0').mock(return_value=httpx.Response(200, text=SEARCH_PAGE))
    results = await Data18MoviesClient().search(SearchContext(title='Big Movie', encoded=q, search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Big Movie'
    assert results[0].scene_url == 'https://www.data18.com/movies/12345'
    assert results[0].subsite == 'ZZ Series'


@respx.mock
async def test_search_direct_id(monkeypatch: pytest.MonkeyPatch, no_web_search: object) -> None:
    monkeypatch.setattr(d18m_module, 'web_search', no_web_search)
    respx.get(url__regex=r'https://www\.data18\.com/sys/live\.php.*').mock(return_value=httpx.Response(200, text='<html>pages: 1</html>'))
    respx.get('https://www.data18.com/movies/12345').mock(return_value=httpx.Response(200, text=MOVIE_PAGE))
    results = await Data18MoviesClient().search(
        SearchContext(title='', encoded='', search_site=SITE.name, site_info=SITE, scene_id='12345', full_title='12345')
    )
    direct = [r for r in results if r.scene_url == 'https://www.data18.com/movies/12345']
    assert direct and direct[0].score == 100
    assert direct[0].title == 'Big Movie'
    assert direct[0].subsite == 'ZZ Series'


@respx.mock
async def test_detail() -> None:
    url = 'https://www.data18.com/movies/12345'
    respx.get(url).mock(return_value=httpx.Response(200, text=MOVIE_PAGE))
    detail = await Data18MoviesClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Big Movie'
    assert detail.studio == 'Empire Studios'
    assert detail.tagline == 'ZZ Series'
    assert detail.collections == ['Empire Studios', 'ZZ Series']
    assert detail.release_date == '2024-01-01'
    assert detail.genres == ['Anal', 'Hardcore']
    assert [(a.name, a.photo_url) for a in detail.actors] == [('Jane Doe', 'https://cdn.example/jane.jpg')]
    assert detail.directors is not None and [d.name for d in detail.directors] == ['Joe Helmer']
    assert 'https://cdn.example/cover.jpg' in detail.raw_image_urls


@respx.mock
async def test_detail_prefers_datetime_attribute() -> None:
    url = 'https://www.data18.com/movies/12345'
    respx.get(url).mock(return_value=httpx.Response(200, text=MOVIE_PAGE_DATETIME))
    detail = await Data18MoviesClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.release_date == '2024-01-05'
    assert detail.studio == 'Empire Studios'
    assert detail.tagline is None


@respx.mock
async def test_detail_strips_reptyle_suffix_and_drops_echoed_subsite() -> None:
    url = 'https://www.data18.com/movies/12345'
    respx.get(url).mock(return_value=httpx.Response(200, text=MOVIE_PAGE_REPTYLE))
    detail = await Data18MoviesClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.studio == 'TeamSkeet'
    assert detail.tagline is None
    assert detail.collections == ['TeamSkeet']


_SEARCH_ID_VS_TITLE = """<html><body>
  pages: 1
  <a href="https://www.data18.com/movies/9999-other-name">
    <p class="gen12 bold">Other Name</p>
    <span class="gen11"><b>#1</b> January, 2024&nbsp;<i>ZZ Series</i></span>
  </a>
  <a href="https://www.data18.com/movies/1234-big-movie">
    <p class="gen12 bold">Big Movie</p>
    <span class="gen11"><b>#2</b> January, 2024&nbsp;<i>ZZ Series</i></span>
  </a>
</body></html>"""


@respx.mock
async def test_scene_id_beats_a_perfect_title_match(monkeypatch: pytest.MonkeyPatch, no_web_search: object) -> None:
    monkeypatch.setattr(d18m_module, 'web_search', no_web_search)
    respx.get(url__regex=r'https://www\.data18\.com/sys/live\.php.*').mock(return_value=httpx.Response(200, text=_SEARCH_ID_VS_TITLE))
    respx.get('https://www.data18.com/movies/9999').mock(return_value=httpx.Response(200, text=MOVIE_PAGE))
    results = await Data18MoviesClient().search(
        SearchContext(title='Big Movie', encoded='Big+Movie', search_site=SITE.name, site_info=SITE, scene_id='9999', full_title='9999 Big Movie')
    )
    by_url = {r.scene_url: r.score for r in results}
    assert by_url['https://www.data18.com/movies/9999'] == 100
    assert by_url['https://www.data18.com/movies/1234'] < 100
