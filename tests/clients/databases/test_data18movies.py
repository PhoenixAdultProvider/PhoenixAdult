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
    <span class="gen11"><b>#1</b> January, 2024&nbsp;<i>Empire Studios</i></span>
  </a>
</body></html>"""

MOVIE_PAGE = """<html><body>
  <h1>Big Movie</h1>
  <p><b>Studio</b>: <b>Empire Studios</b></p>
  <div class="gen12"><div>Description --- A grand description. Studio: Empire Studios</div></div>
  <p><b>Categories</b>: <a>Anal</a><a>Hardcore</a></p>
  <time datetime="2024-01-05"></time>
  <a href="/pornstars/jane"><img alt="Jane Doe" data-src="https://cdn.example/jane.jpg" /></a>
  <p><b>Director</b>: Joe Helmer</p>
  <a id="enlargecover" data-featherlight="https://cdn.example/cover.jpg"></a>
</body></html>"""


async def _no_web_search(*_args: object, **_kwargs: object) -> list[str]:
    return []


@respx.mock
async def test_search_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(d18m_module, 'web_search', _no_web_search)
    q = quote('Big Movie')
    respx.get(f'https://www.data18.com/sys/live.php?index=&key={q}&key2={q}&next=1&page=0').mock(return_value=httpx.Response(200, text=SEARCH_PAGE))
    results = await Data18MoviesClient().search(SearchContext(title='Big Movie', encoded=q, search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Big Movie'
    assert results[0].scene_url == 'https://www.data18.com/movies/12345'


@respx.mock
async def test_search_direct_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(d18m_module, 'web_search', _no_web_search)
    respx.get(url__regex=r'https://www\.data18\.com/sys/live\.php.*').mock(return_value=httpx.Response(200, text='<html>pages: 1</html>'))
    respx.get('https://data18.com/movies/12345').mock(return_value=httpx.Response(200, text=MOVIE_PAGE))
    results = await Data18MoviesClient().search(
        SearchContext(title='', encoded='', search_site=SITE.name, site_info=SITE, scene_id='12345', full_title='12345')
    )
    direct = [r for r in results if r.scene_url == 'https://data18.com/movies/12345']
    assert direct and direct[0].score == 100


@respx.mock
async def test_detail() -> None:
    url = 'https://data18.com/movies/12345'
    respx.get(url).mock(return_value=httpx.Response(200, text=MOVIE_PAGE))
    detail = await Data18MoviesClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Big Movie'
    assert detail.studio == 'Empire Studios'
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['Anal', 'Hardcore']
    assert [(a.name, a.photo_url) for a in detail.actors] == [('Jane Doe', 'https://cdn.example/jane.jpg')]
    assert detail.directors is not None and [d.name for d in detail.directors] == ['Joe Helmer']
    assert 'https://cdn.example/cover.jpg' in detail.raw_image_urls
