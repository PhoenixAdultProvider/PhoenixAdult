from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.networks.czechvr import CzechVRClient, __testing__
from phoenixadult.registry import find_site

SITE = find_site('CzechVR')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '%20'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search_scene_id_score() -> None:
    url = 'https://czechvr.com/searching?search=cool%20scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<div class="postTag">
              <a href="/video/555-cool-scene"></a>
              <div class="nazev"><h2><a>555 - Cool Scene</a></h2></div>
              <div class="datum">Mar 4, 2021</div>
              <img data-src="https://cdn/cdn-cgi/image/w=100/thumb.jpg" />
            </div>""",
        )
    )
    results: list[SearchResult] = []
    await CzechVRClient().search(results, _ctx(scene_id='555'))
    assert len(results) == 1
    assert results[0].title == '555 - Cool Scene'
    assert results[0].scene_url == 'https://czechvr.com/video/555-cool-scene'
    assert results[0].score == 100
    assert results[0].thumb_url == 'https://cdn/cdn-cgi/image//thumb.jpg'


@respx.mock
async def test_detail() -> None:
    url = 'https://czechvr.com/video/555-cool-scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <div class="nazev"><h1>555 - Cool Scene Czech VR</h1>
                <div class="datum">Mar 4, 2021</div>
                <div class="featuring"><a>Jane Doe</a></div>
              </div>
              <div class="text">A summary.</div>
              <div class="tag new"><a>VR</a></div><div class="tag"><a>180</a></div>
              <div class="modelky"><a>Jane Doe</a></div>
              <div class="galerka"><a href="https://cdn/g1.jpg"></a></div>
            </body></html>""",
        )
    )
    detail = await CzechVRClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'CzechVR'
    assert detail.tagline == 'CzechVR'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['vr', '180']
    assert [a.name for a in detail.actors] == ['Jane Doe']
    assert detail.art == ['https://cdn/g1.jpg']


def test_strip_brand() -> None:
    assert __testing__['strip_brand']('Cool Scene Czech VR') == 'Cool Scene'
    assert __testing__['strip_brand']('X Czech VR Casting') == 'X'
