from __future__ import annotations

import httpx
import pytest
import respx

from app.clients.base import SearchContext
from app.clients.sites import sexlikereal as slr_module
from app.clients.sites.sexlikereal import SexLikeRealClient
from app.registry import find_site

SITE = find_site('Sex Like Real')
assert SITE is not None

DETAIL_HTML = """<html><head><meta property="og:image" content="https://cdn.slr.com/cover.webp"></head><body>
  <h1>VR Real</h1>
  <p class="_s1jg1wcd75 x">A blurb.</p>
  <p class="_s1jg1wcd75 x">Video specifications: 4K</p>
  <a class="_euacs6n160 y">SLR Originals</a>
  <p class="_38471wcd31 z"><time datetime="2021-09-09">Sep 9</time></p>
  <a class="_1xdu1wcd88"><span>VR</span></a><a class="_1xdu1wcd88"><span>POV</span></a>
  <a class="_n7wm1ua719" href="/pornstars/alice">Alice</a>
  <img class="_30hk1wta22" src="https://cdn.slr.com/c1.webp">
</body></html>"""

ACTOR_HTML = '<html><body><div class="_z763mqyu24 avatar avatar-size-32 outlined"><img src="https://cdn.slr.com/alice.jpg"></div></body></html>'


async def _no_web(*_a: object, **_k: object) -> list[str]:
    return []


@respx.mock
async def test_search_direct_slug(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(slr_module, 'web_search_urls', _no_web)
    url = 'https://www.sexlikereal.com/scenes/vr-real'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    results = await SexLikeRealClient().search(SearchContext(title='VR Real', encoded='', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'VR Real'
    assert results[0].scene_url == url
    assert results[0].score == 100
    assert results[0].release_date == '2021-09-09'


@respx.mock
async def test_detail_fields_actors_images() -> None:
    url = 'https://www.sexlikereal.com/scenes/vr-real'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    respx.get('https://www.sexlikereal.com/pornstars/alice').mock(return_value=httpx.Response(200, text=ACTOR_HTML))
    detail = await SexLikeRealClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'VR Real'
    assert detail.summary == 'A blurb.'  # 'Video specifications' paragraph skipped
    assert detail.studio == 'SLR Originals'
    assert detail.collections == ['SLR Originals']
    assert detail.release_date == '2021-09-09'
    assert detail.genres == ['VR', 'POV']
    assert [a.name for a in detail.actors] == ['Alice']
    assert detail.actors[0].photo_url == 'https://cdn.slr.com/alice.jpg'
    # og:image + cover, webp -> jpg
    assert detail.raw_image_urls == ['https://cdn.slr.com/cover.jpg', 'https://cdn.slr.com/c1.jpg']
