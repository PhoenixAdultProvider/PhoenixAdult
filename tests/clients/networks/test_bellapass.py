from __future__ import annotations

import httpx
import pytest
import respx

import app.clients.networks.bellapass as bp_mod
from app.clients.base import SearchContext
from app.clients.networks.bellapass import BellaPassClient, __testing__
from app.registry import find_site

BELLA = find_site('BellaPass')
HUSSIE = find_site('Hussie Pass')
assert BELLA is not None and HUSSIE is not None


def _ctx(site: object, title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '%20'), search_site=site.name, site_info=site, **kw)  # type: ignore[union-attr,arg-type]


@respx.mock
async def test_search_direct_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bp_mod, 'web_search_available', lambda: False)
    respx.get('https://bellapass.com/search.php?query=cool-scene').mock(return_value=httpx.Response(200, text='<html></html>'))
    respx.get('https://bellapass.com/trailers/cool-scene.html').mock(
        return_value=httpx.Response(
            200,
            text='<h3>Cool Scene</h3><div class="videoInfo"><p>Mar 4, 2021</p></div>',
        )
    )
    results = await BellaPassClient().search(_ctx(BELLA))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://bellapass.com/trailers/cool-scene.html'
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_detail_umbrella() -> None:
    url = 'https://bellapass.com/trailers/cool-scene.html'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h3>Cool Scene</h3>
              <div class="videoDetails"><p>A summary.</p></div>
              <div class="videoInfo"><p>Mar 4, 2021</p></div>
              <div class="featuring">
                <a href="/categories/anal">Anal</a>
                <a href="/models/jane">Jane Doe!</a>
                <a href="/models/john">John Smith</a>
                <a href="/models/jack">Jack</a>
              </div>
              <img class="thumbs" id="set9" src0_3x="/img/t1.jpg" />
            </body></html>""",
        )
    )
    respx.get('https://bellapass.com/models/jane').mock(return_value=httpx.Response(200, text='<div class="profile-pic"><img src0_3x="/p/jane.jpg" /></div>'))
    respx.get('https://bellapass.com/models/john').mock(return_value=httpx.Response(200, text='<div></div>'))
    respx.get('https://bellapass.com/models/jack').mock(return_value=httpx.Response(200, text='<div></div>'))
    respx.get('https://bellapass.com/search.php?query=Cool+Scene').mock(
        return_value=httpx.Response(200, text='<img id="set9" cnt="2" src0_3x="/img/s0.jpg" src1_3x="/img/s1.jpg" />')
    )
    respx.get('https://bellapass.com/preview/cool-scene.html').mock(return_value=httpx.Response(200, text='<img id="set9" src0_3x="/img/pv.jpg" />'))
    detail = await BellaPassClient().fetch_scene_detail(url, BELLA)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'BellaPass'
    assert detail.tagline == 'BellaPass'  # umbrella keeps a tagline
    assert detail.collections == ['BellaPass']
    assert detail.genres == ['Anal', 'Threesome']  # 3 models → Threesome
    assert [a.name for a in detail.actors] == ['Jane Doe', 'John Smith', 'Jack']  # punctuation stripped
    assert detail.actors[0].photo_url == 'https://bellapass.com/p/jane.jpg'
    assert detail.raw_image_urls == [
        'https://bellapass.com/img/t1.jpg',
        'https://bellapass.com/img/s0.jpg',
        'https://bellapass.com/img/s1.jpg',
        'https://bellapass.com/img/pv.jpg',
    ]


@respx.mock
async def test_detail_subbrand_is_own_studio() -> None:
    url = 'https://hussiepass.com/trailers/x.html'
    respx.get(url).mock(return_value=httpx.Response(200, text='<h1>Sub Scene</h1>'))
    detail = await BellaPassClient().fetch_scene_detail(url, HUSSIE)
    assert detail is not None
    assert detail.title == 'Sub Scene'  # h1 selector for Hussie Pass
    assert detail.studio == 'Hussie Pass'  # sub-brand is its own studio
    assert detail.tagline is None  # no tagline for sub-brands
    assert detail.collections == ['Hussie Pass']


def test_helpers() -> None:
    assert __testing__['strip_punct']('Jane Doe!') == 'Jane Doe'
    assert __testing__['studio_for']('Hussie Pass') == 'Hussie Pass'
    assert __testing__['studio_for']('BellaPass') == 'BellaPass'
    assert __testing__['title_selector_for']('See Him Fuck') == 'h1'
    assert __testing__['title_selector_for']('BellaPass') == 'h3'
