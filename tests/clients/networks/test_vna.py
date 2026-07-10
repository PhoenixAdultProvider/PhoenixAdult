from __future__ import annotations

import httpx
import pytest
import respx

import app.clients.networks.vna as mod
from app.clients.base import SearchContext
from app.clients.networks.vna import VNAClient
from app.registry import find_site

SITE = find_site('Sara Jay')
assert SITE is not None


def _ctx(title: str = '12345', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title, search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


_SCENE = """<html><body>
  <h1 class="customhcolor">Cool Scene</h1>
  <div class="customhcolor2">A summary.</div>
  <span class="date">March 4, 2021</span>
  <h4 class="customhcolor">Anal, Teen</h4>
  <h3 class="customhcolor">Jane Doe, John Smith XXX</h3>
  <center><img src="img/thumb_1.jpg" /></center>
</body></html>"""


@respx.mock
async def test_search_by_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, 'web_search_available', lambda: False)
    respx.get('https://sarajay.com/videos/12345').mock(return_value=httpx.Response(200, text=_SCENE))
    results = await VNAClient().search(_ctx(scene_id='12345'))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://sarajay.com/videos/12345'


@respx.mock
async def test_detail() -> None:
    url = 'https://sarajay.com/videos/36260/cool-scene'
    respx.get(url).mock(return_value=httpx.Response(200, text=_SCENE))
    detail = await VNAClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'VNA Network'
    assert detail.tagline == 'Sara Jay'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Anal', 'Teen']
    names = [a.name for a in (detail.actors or [])]
    assert names == ['Jane Doe', 'John Smith', 'Sarah Arabic']
    assert detail.raw_image_urls == ['https://sarajay.com/img/thumb_1.jpg', 'https://sarajay.com/img/thumb_2.jpg', 'https://sarajay.com/img/thumb_3.jpg']
