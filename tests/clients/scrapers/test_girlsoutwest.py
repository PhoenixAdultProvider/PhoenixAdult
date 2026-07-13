from __future__ import annotations

import httpx
import pytest
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites import girlsoutwest as gow_module
from app.clients.sites.girlsoutwest import GirlsOutWestClient
from app.registry import find_site

SITE = find_site('GirlsOutWest')
assert SITE is not None

DETAIL_HTML = r"""<html><head>
  <meta name="twitter:title" content="Outback Fun">
</head><body>
  <div class="trailer topSpace"><div></div><div><p>Featuring <a href="/models/alice">Alice</a> \ 03/04/2021</p></div></div>
  <div class="videoplayer"><img src0_3x="/img/p1.jpg"></div>
</body></html>"""


async def _no_web(*_a: object, **_k: object) -> list[str]:
    return []


@respx.mock
async def test_search_direct_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gow_module, 'web_search_urls', _no_web)
    url = 'https://tour.girlsoutwest.com/trailers/outback-fun.html'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    results: list[SearchResult] = []
    await GirlsOutWestClient().search(results, SearchContext(title='Outback Fun', encoded='', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Outback Fun'
    assert results[0].scene_url == url
    assert results[0].release_date == '2021-03-04'


@respx.mock
async def test_detail_fields_actors_genres_images() -> None:
    url = 'https://tour.girlsoutwest.com/trailers/outback-fun.html'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    actor_html = '<html><body><div class="profilePic"><img src0_3x="/img/alice.jpg"></div></body></html>'
    respx.get('https://tour.girlsoutwest.com/models/alice').mock(return_value=httpx.Response(200, text=actor_html))
    detail = await GirlsOutWestClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Outback Fun'
    assert detail.studio == 'GirlsOutWest'
    assert detail.collections == ['GirlsOutWest']
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Amateur', 'Australian']
    assert len(detail.actors) == 1
    assert detail.actors[0].name == 'Alice'
    assert detail.actors[0].photo_url == 'https://tour.girlsoutwest.com/img/alice.jpg'
    assert detail.art == ['https://tour.girlsoutwest.com/img/p1.jpg']
