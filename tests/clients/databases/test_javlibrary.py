from __future__ import annotations

import httpx
import pytest
import respx

import app.clients.aggregators.javlibrary as jl_module
from app.clients.aggregators.javlibrary import JavLibraryClient
from app.clients.base import SearchContext
from app.registry import find_site

SITE = find_site('JAVLibrary')
assert SITE is not None


async def _no_web_search(*_args: object, **_kwargs: object) -> list[str]:
    return []


@respx.mock
async def test_search_video_cards(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jl_module, 'web_search', _no_web_search)
    respx.get('https://www.javlibrary.com/en/vl_searchbyid.php?keyword=ABP-060').mock(
        return_value=httpx.Response(200, text='<html><body><div class="video"><a title="ABP-060 Some Movie" href="./?v=javabc"></a></div></body></html>')
    )
    results = await JavLibraryClient().search(SearchContext(title='ABP 060', encoded='ABP%20060', search_site=SITE.name, site_info=SITE))
    hit = next((r for r in results if r.scene_url == 'https://www.javlibrary.com/en/?v=javabc'), None)
    assert hit is not None
    assert hit.title == '[ABP-060] ABP-060 Some Movie'


@respx.mock
async def test_search_web_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _ws(opts: object) -> list[str]:
        return ['https://www.javlibrary.com/ja/?v=javxyz']

    monkeypatch.setattr(jl_module, 'web_search', _ws)
    respx.get('https://www.javlibrary.com/en/vl_searchbyid.php?keyword=XYZ-789').mock(return_value=httpx.Response(404, text=''))
    respx.get('https://www.javlibrary.com/en/?v=javxyz').mock(
        return_value=httpx.Response(
            200,
            text="""<html><head><meta property="og:url" content="//www.javlibrary.com/en/?v=javxyz"></head><body>
              <h3 class="post-title text"><a>XYZ-789 The Movie Title</a></h3>
              <table><tr><td>ID:</td><td>XYZ-789</td></tr></table>
            </body></html>""",
        )
    )
    results = await JavLibraryClient().search(SearchContext(title='XYZ 789', encoded='XYZ%20789', search_site=SITE.name, site_info=SITE))
    hit = next((r for r in results if r.scene_url == 'https://www.javlibrary.com/en/?v=javxyz'), None)
    assert hit is not None
    assert hit.title == '[XYZ-789] The Movie Title'


@respx.mock
async def test_detail() -> None:
    url = 'https://www.javlibrary.com/en/?v=javabc'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><head><meta property="og:title" content="ABP-060 Some Movie - JAVLibrary"></head><body>
              <table><tr><td>Maker:</td><td><span><a>Prestige</a></span></td></tr>
              <tr><td>Label:</td><td><span><a>ABP Label</a></span></td></tr>
              <tr><td>Release Date:</td><td>2024-01-05</td></tr></table>
              <a rel="category tag">Drama</a>
              <span class="star"><a>Jane Doe</a></span>
              <img id="video_jacket_img" src="//pics.example/jacket.jpg"/>
            </body></html>""",
        )
    )
    respx.get('https://www.javbus.com/en/ABP-060').mock(return_value=httpx.Response(200, text='<html><body></body></html>'))
    detail = await JavLibraryClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == '[ABP-060] Some Movie'
    assert detail.studio == 'Prestige'
    assert detail.tagline == 'ABP Label'
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['Drama']
    assert [a.name for a in detail.actors] == ['Jane Doe']
    assert 'https://pics.example/jacket.jpg' in detail.raw_image_urls
