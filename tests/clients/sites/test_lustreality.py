from __future__ import annotations

import httpx
import pytest
import respx

from phoenixadult.clients.sites import lustreality as lr_module
from phoenixadult.clients.sites.lustreality import LustRealityClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site
from tests.support import served_collections

SITE = find_site('Lust Reality')
assert SITE is not None

DETAIL_HTML = """<html><body>
  <h1>VR Lust</h1>
  <div class="u-mb--six">A blurb.</div>
  <span class="date-display-single">2021-04-04</span>
  <a href="/list/category/vr">VR</a><a href="/list/category/pov">POV</a>
  <a href="/pornstars/model/alice">Alice</a>
  <div class="splash-screen" style="background-image: url('https://cdn.lr.com/bg.jpg')"></div>
  <a class="u-ratio--lightbox" href="/img/g1.jpg">x</a>
</body></html>"""

ACTOR_HTML = '<html><body><div class="u-ratio--model-poster"><img data-src="https://cdn.lr.com/alice.jpg"></div></body></html>'


async def _no_web(*_a: object, **_k: object) -> list[str]:
    return []


@respx.mock
async def test_search_direct_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lr_module, 'web_search_urls', _no_web)
    url = 'https://www.lustreality.com/virtualreality/scene/id/vr-lust'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    results: list[SearchResult] = []
    await LustRealityClient().search(results, SearchContext(title='VR Lust', encoded='', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'VR Lust'
    assert results[0].scene_url == url
    assert results[0].release_date == '2021-04-04'


@respx.mock
async def test_detail_fields_actors_images() -> None:
    url = 'https://www.lustreality.com/virtualreality/scene/id/vr-lust'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    respx.get('https://www.lustreality.com/pornstars/model/alice').mock(return_value=httpx.Response(200, text=ACTOR_HTML))
    detail = await LustRealityClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'VR Lust'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'Lust Reality'
    assert served_collections(detail) == ['Lust Reality']
    assert detail.release_date == '2021-04-04'
    assert detail.genres == ['VR', 'POV']
    assert [a.name for a in detail.actors] == ['Alice']
    assert detail.actors[0].photo_url == 'https://cdn.lr.com/alice.jpg'
    assert detail.art == ['https://cdn.lr.com/bg.jpg', 'https://www.lustreality.com/img/g1.jpg']
