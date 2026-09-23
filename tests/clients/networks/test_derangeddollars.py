from __future__ import annotations

import httpx
import pytest
import respx

import phoenixadult.clients.networks.derangeddollars as dd_mod
from phoenixadult.clients import base as client_base
from phoenixadult.models.scrape import SearchResult
from phoenixadult.registry import find_site
from tests.support import search_context


async def _no_web_search(*_a: object, **_k: object) -> list[str]:
    return []


SITE = find_site('Deranged Dollars')
assert SITE is not None


@respx.mock
async def test_search(monkeypatch: pytest.MonkeyPatch) -> None:

    async def fake_filtered(*_a: object, **_k: object) -> list[str]:
        return ['https://derangeddollars.com/session/77/cool-scene']

    monkeypatch.setattr(client_base, 'web_search_urls', fake_filtered)
    respx.get('https://derangeddollars.com/session/77/cool-scene').mock(
        return_value=httpx.Response(200, text='<h3 class="mas_title">Cool Scene</h3><div class="lch"><span>Nurse Jane, March 4, 2021</span></div>')
    )
    results: list[SearchResult] = []
    await dd_mod.DerangedDollarsClient().search(results, search_context(SITE, 'cool scene', space='%20'))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://derangeddollars.com/session/77/cool-scene'
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_search_no_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_base, 'web_search_urls', _no_web_search)
    results: list[SearchResult] = []
    await dd_mod.DerangedDollarsClient().search(results, search_context(SITE, 'cool scene', space='%20'))
    assert results == []


@respx.mock
async def test_detail() -> None:
    url = 'https://derangeddollars.com/session/77/cool-scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><head><title>Cool Scene | derangeddollars.com</title></head><body>
              <h3 class="mas_title">Cool Scene</h3>
              <p class="mas_longdescription">A summary.</p>
              <p class="tags"><a>Anal</a><a>Fetish</a></p>
              <div class="lch"><span>Cast: Jane Doe & John Smith, March 4, 2021</span></div>
              <div class="stills clearfix"><img src="/img/s1.jpg" /></div>
              <div class="mainpic"><script>var x = 'https://cdn/main.jpg';</script></div>
            </body></html>""",
        )
    )
    respx.get('https://derangeddollars.com/?models').mock(
        return_value=httpx.Response(200, text='<div class="item">Model: Jane Doe<img src="/p/jane.jpg" /></div>')
    )
    respx.get('https://derangeddollars.com/?models/2').mock(return_value=httpx.Response(200, text='<div></div>'))
    detail = await dd_mod.DerangedDollarsClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Deranged Dollars'
    assert detail.tagline == 'derangeddollars'
    assert detail.collections == ['derangeddollars']
    assert detail.genres == ['Anal', 'Fetish']
    assert [a.name for a in detail.actors] == ['Jane Doe', 'John Smith']
    assert detail.actors[0].photo_url == 'https://derangeddollars.com/p/jane.jpg'
    assert detail.art == ['https://derangeddollars.com/img/s1.jpg', 'https://cdn/main.jpg']
