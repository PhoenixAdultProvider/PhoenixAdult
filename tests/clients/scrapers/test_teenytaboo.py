from __future__ import annotations

import httpx
import pytest
import respx

import phoenixadult.clients.sites.teenytaboo as tt_module
from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.sites.teenytaboo import TeenyTabooClient
from phoenixadult.registry import find_site

SITE = find_site('Teeny Taboo')
assert SITE is not None

SCENE_HTML = """<html><body>
  <h1 class="customhcolor">wild-scene-title</h1>
  <h2 class="customhcolor2">A scene blurb.</h2>
  <h3>Jane Doe, Mary Roe and Sue Smith</h3>
  <center><img src="/img/poster.jpg" /></center>
</body></html>"""


@respx.mock
async def test_search_direct_candidate(monkeypatch: pytest.MonkeyPatch, no_web_search: object) -> None:
    monkeypatch.setattr(tt_module, 'web_search_urls', no_web_search)
    respx.get('https://teenytaboo.com/video/wild-scene').mock(return_value=httpx.Response(200, text=SCENE_HTML))
    results: list[SearchResult] = []
    await TeenyTabooClient().search(results, SearchContext(title='Wild Scene', encoded='Wild%20Scene', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'wild scene title'
    assert results[0].scene_url == 'https://teenytaboo.com/video/wild-scene'


@respx.mock
async def test_detail() -> None:
    url = 'https://teenytaboo.com/video/wild-scene'
    respx.get(url).mock(return_value=httpx.Response(200, text=SCENE_HTML))
    detail = await TeenyTabooClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'wild scene title'
    assert detail.summary == 'A scene blurb.'
    assert detail.studio == 'Teeny Taboo'
    assert detail.tagline is None
    assert detail.collections == ['Teeny Taboo']
    assert [a.name for a in detail.actors] == ['Jane Doe', 'Mary Roe', 'Sue Smith']
    assert detail.art == ['https://teenytaboo.com/img/poster.jpg']
