from __future__ import annotations

import httpx
import pytest
import respx

from phoenixadult.clients.sites import heavyonhotties as hoh_module
from phoenixadult.clients.sites.heavyonhotties import HeavyOnHottiesClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site

SITE = find_site('Heavy on Hotties')
assert SITE is not None

DETAIL_HTML = """<html><body>
  <h1>Heavy on Hotties: Alice and Bob - Wild Night</h1>
  <div class="video_text">A blurb.</div>
  <span class="released title"><strong>2021-08-08</strong></span>
  <span class="feature title"><a href="/models/alice">Alice</a></span>
  <video poster="//cdn.hoh.com/poster.jpg"></video>
</body></html>"""

ACTOR_HTML = '<html><body><div><h1>Alice</h1><img src="//cdn.hoh.com/alice.jpg"></div></body></html>'


async def _no_web(*_a: object, **_k: object) -> list[str]:
    return []


@respx.mock
async def test_search_direct_variant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hoh_module, 'web_search_urls', _no_web)
    url = 'https://www.heavyonhotties.com/movies/alice-bob-wild-night'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    respx.get('https://www.heavyonhotties.com/movies/bob-wild-night').mock(return_value=httpx.Response(404))
    respx.get('https://www.heavyonhotties.com/movies/wild-night').mock(return_value=httpx.Response(404))
    results: list[SearchResult] = []
    await HeavyOnHottiesClient().search(results, SearchContext(title='Alice Bob Wild Night', encoded='', search_site=SITE.name, site_info=SITE))
    assert any(r.scene_url == url for r in results)
    hit = next(r for r in results if r.scene_url == url)
    assert hit.title == 'Alice and Bob - Wild Night'
    assert hit.release_date == '2021-08-08'


@respx.mock
async def test_detail_title_actors_images() -> None:
    url = 'https://www.heavyonhotties.com/movies/wild-night'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    respx.get('https://www.heavyonhotties.com/models/alice').mock(return_value=httpx.Response(200, text=ACTOR_HTML))
    detail = await HeavyOnHottiesClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Wild Night'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'Heavy on Hotties'
    assert detail.collections == ['Heavy on Hotties']
    assert detail.release_date == '2021-08-08'
    assert [a.name for a in detail.actors] == ['Alice']
    assert detail.actors[0].photo_url == 'https://cdn.hoh.com/alice.jpg'
    assert detail.art == ['https://cdn.hoh.com/poster.jpg']
