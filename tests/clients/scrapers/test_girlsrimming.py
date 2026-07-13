from __future__ import annotations

import httpx
import pytest
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites import girlsrimming as gr_module
from app.clients.sites.girlsrimming import GirlsRimmingClient
from app.registry import find_site

SITE = find_site('Girls Rimming')
assert SITE is not None

DETAIL_HTML = """<html><head>
  <meta name="description" content="A blurb.">
  <meta name="keywords" content="deep rimming, sloppy, Alice Star Id 99, anal">
</head><body>
  <h2 class="title">Rim Session<span>badge</span></h2>
  <div id="fakeplayer"><img src0_3x="/img/p1.jpg"></div>
</body></html>"""

ACTOR_HTML = '<html><body><div class="model_picture"><img src0_3x="/img/alice.jpg"></div></body></html>'


async def _no_web(*_a: object, **_k: object) -> list[str]:
    return []


@respx.mock
async def test_search_direct_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gr_module, 'web_search_urls', _no_web)
    url = 'https://www.girlsrimming.com/tour/trailers/rim-session.html'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    results: list[SearchResult] = []
    await GirlsRimmingClient().search(results, SearchContext(title='Rim Session', encoded='', search_site=SITE.name, site_info=SITE, search_date='2021-05-05'))
    assert len(results) == 1
    assert results[0].title == 'Rim Session'
    assert results[0].scene_url == url


@respx.mock
async def test_detail_genres_actors_images(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gr_module, 'web_search_urls', _no_web)
    url = 'https://www.girlsrimming.com/tour/trailers/rim-session.html'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    respx.get('https://www.girlsrimming.com/tour/models/alice-star.html').mock(return_value=httpx.Response(200, text=ACTOR_HTML))
    detail = await GirlsRimmingClient().fetch_scene_detail(f'{url}|2021-05-05', SITE)
    assert detail is not None
    assert detail.title == 'Rim Session'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'Girls Rimming'
    assert detail.release_date == '2021-05-05'
    assert detail.genres == ['Deep Rimming', 'Sloppy', 'Anal', 'Rim Job']
    assert [a.name for a in detail.actors] == ['Alice Star']
    assert detail.actors[0].photo_url == 'https://www.girlsrimming.com/img/alice.jpg'
    assert detail.art == ['https://www.girlsrimming.com/img/p1.jpg']
