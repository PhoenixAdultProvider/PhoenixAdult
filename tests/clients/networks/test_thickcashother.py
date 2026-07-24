from __future__ import annotations

import httpx
import pytest
import respx

import phoenixadult.clients.networks.thickcashother as mod
from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.networks.thickcashother import ThickCashOtherClient
from phoenixadult.registry import find_site

SITE = find_site('MilfAF')
assert SITE is not None

_SCENE = """<html><body>
  <h3 class="top-title">Cool Scene</h3>
  <div class="player-box"><p>A summary.</p></div>
  <a class="tag" href="/models/jane-doe">Jane Doe</a>
  <video poster="https://cdn/p.jpg"></video>
</body></html>"""


def _ctx(title: str = 'Jane Doe Cool Scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search_and_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _no_web(*_a: object, **_k: object) -> list[str]:
        return []

    monkeypatch.setattr(mod, 'web_search_urls', _no_web)
    respx.get('https://milfaf.com/videos/jane-doe-cool-scene.html').mock(return_value=httpx.Response(200, text=_SCENE))
    respx.get('https://milfaf.com/models/Jane-Doe.html').mock(return_value=httpx.Response(404, text=''))

    results: list[SearchResult] = []
    await ThickCashOtherClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://milfaf.com/videos/jane-doe-cool-scene.html'

    detail = await ThickCashOtherClient().fetch_scene_detail(ThickCashOtherClient().decode(results[0].cur_id), SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Thick Cash'
    assert detail.tagline == 'MilfAF'
    assert detail.actors is not None and detail.actors[0].name == 'Jane Doe'
    assert detail.art == ['https://cdn/p.jpg']
