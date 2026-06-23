from __future__ import annotations

from urllib.parse import quote

import httpx
import pytest
import respx

import app.clients.aggregators.data18scenes as d18s_module
from app.clients.aggregators.data18scenes import Data18ScenesClient
from app.clients.base import SearchContext
from app.registry import find_site

SITE = find_site('Data18 Scenes')
assert SITE is not None

SEARCH_PAGE = """<html><body>
  pages: 1
  <a href="https://www.data18.com/scenes/9999-fun-scene">
    <p class="gen12 bold">Fun Scene</p>
    <span class="gen11"><b>#1</b> January 5, 2024&nbsp;<i>TeamSkeet</i></span>
  </a>
</body></html>"""

SCENE_PAGE = """<html><body>
  <h1>Scene 3: Fun Scene</h1>
  <p><b>Studio</b><b>TeamSkeet</b></p>
  <p><b>Network</b><a>Teen Pies</a></p>
  <span>Release date</span><a><b>Jan 5, 2024</b></a>
  <div><b>Categories</b><a>Teen</a><a>Hardcore</a></div>
  <h3>Cast</h3>
  <div><a href="/name/jane"><img alt="Jane Doe" /></a></div>
</body></html>"""


async def _no_web_search(*_args: object, **_kwargs: object) -> list[str]:
    return []


@respx.mock
async def test_search_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(d18s_module, 'web_search', _no_web_search)
    q = quote('Fun Scene')
    respx.get(f'https://www.data18.com/sys/live.php?index=&key={q}&key2={q}&next=1&page=0').mock(return_value=httpx.Response(200, text=SEARCH_PAGE))
    results = await Data18ScenesClient().search(SearchContext(title='Fun Scene', encoded=q, search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Fun Scene'
    assert results[0].scene_url == 'https://www.data18.com/scenes/9999'


@respx.mock
async def test_search_direct_scene_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(d18s_module, 'web_search', _no_web_search)
    # The empty-query candidate search yields nothing; mock it as empty.
    respx.get(url__regex=r'https://www\.data18\.com/sys/live\.php.*').mock(return_value=httpx.Response(200, text='<html>pages: 1</html>'))
    respx.get('https://data18.com/scenes/9999').mock(return_value=httpx.Response(200, text=SCENE_PAGE))
    results = await Data18ScenesClient().search(SearchContext(title='', encoded='', search_site=SITE.name, site_info=SITE, scene_id='9999', full_title='9999'))
    direct = [r for r in results if r.scene_url == 'https://data18.com/scenes/9999']
    assert direct and direct[0].score == 100


@respx.mock
async def test_detail() -> None:
    url = 'https://data18.com/scenes/9999'
    respx.get(url).mock(return_value=httpx.Response(200, text=SCENE_PAGE))
    detail = await Data18ScenesClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Fun Scene - Scene 3'
    assert detail.studio == 'TeamSkeet'
    assert detail.tagline == 'Teen Pies'
    assert detail.collections == ['Teen Pies']
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['Teen', 'Hardcore']
    assert [a.name for a in detail.actors] == ['Jane Doe']
