from __future__ import annotations

import httpx
import pytest
import respx

import phoenixadult.clients.sites.vrlatina as vrl_module
from phoenixadult.clients.sites.vrlatina import VRLatinaClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site
from tests.support import served_collections

SITE = find_site('VR Latina')
assert SITE is not None


@respx.mock
async def test_search_direct_og_title(monkeypatch: pytest.MonkeyPatch, no_web_search: object) -> None:
    monkeypatch.setattr(vrl_module, 'web_search_urls', no_web_search)
    url = 'https://vrlatina.com/video/wild-scene.html'
    respx.get(url).mock(return_value=httpx.Response(200, text='<html><head><meta property="og:title" content="Wild Scene" /></head></html>'))
    results: list[SearchResult] = []
    await VRLatinaClient().search(results, SearchContext(title='Wild Scene', encoded='x', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].scene_url == url
    assert results[0].title == 'Wild Scene'


@respx.mock
async def test_detail() -> None:
    url = 'https://vrlatina.com/video/wild-scene.html'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><head><meta property="og:image" content="//cdn.vrl.com/og.jpg" /></head><body>
              <h2>Wild Scene</h2>
              <div class="content-desc">A blurb.</div>
              <div class="content-base-info"><div class="info-elem -length"><span>Jan 5, 2024</span></div></div>
              <div class="content-links -tags"><a title="Anal">Anal</a><a title="Hardcore">Hardcore</a></div>
              <div class="content-links -models"><a title="Jane Doe" href="https://vrlatina.com/model/jane">Jane Doe</a></div>
              <a class="video-gallery-item" href="//cdn.vrl.com/g1.jpg">g1</a>
              <a class="video-gallery-item" href="//cdn.vrl.com/g2.jpg">g2</a>
            </body></html>""",
        )
    )
    respx.get('https://vrlatina.com/model/jane').mock(
        return_value=httpx.Response(200, text='<html><body><div class="model-avatar"><img src="https://cdn.vrl.com/jane.jpg" /></div></body></html>')
    )
    detail = await VRLatinaClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Wild Scene'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'VR Latina'
    assert detail.tagline == ''
    assert served_collections(detail) == ['VR Latina']
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['Anal', 'Hardcore']
    assert [(a.name, a.photo_url) for a in detail.actors] == [('Jane Doe', 'https://cdn.vrl.com/jane.jpg')]
    assert detail.art == ['https://cdn.vrl.com/g1.jpg', 'https://cdn.vrl.com/g2.jpg', 'https://cdn.vrl.com/og.jpg']
