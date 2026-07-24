from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.networks.hightechvr import HighTechVRClient, _rewrite_sexbabes
from phoenixadult.registry import find_site

SITE = find_site('RealJamVR')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '%20'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search_direct() -> None:
    url = 'https://realjamvr.com/scene/cool-scene'
    respx.get(url).mock(return_value=httpx.Response(200, text='<h1>Cool Scene</h1>'))
    results: list[SearchResult] = []
    await HighTechVRClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == url
    assert results[0].score == 100


@respx.mock
async def test_detail() -> None:
    url = 'https://realjamvr.com/scene/cool-scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><head><title>Some Studio | Cool Scene</title></head><body>
              <h1>Cool Scene</h1>
              <div class="opacity-75 my-2">A summary.</div>
              <div class="ms-4 text-nowrap">March 4, 2021</div>
              <div class="my-2 lh-lg"><a>VR</a><a>180</a></div>
              <div class="scene-view mx-auto"><a href="/models/jane">Jane Doe</a></div>
              <img class="img-thumb" src="https://cdn/g1.jpg?token=x" />
              <dl8-video poster="https://cdn/poster.jpg?token=y"></dl8-video>
            </body></html>""",
        )
    )
    respx.get('https://realjamvr.com/models/jane').mock(
        return_value=httpx.Response(200, text='<div class="col-12 col-lg-4 pe-lg-0"><img src="https://cdn/jane.jpg" /></div>')
    )
    detail = await HighTechVRClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'RealJamVR'
    assert detail.tagline == 'Cool Scene'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['VR', '180']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://cdn/jane.jpg'
    assert detail.art == ['https://cdn/g1.jpg?token=x', 'https://cdn/poster.jpg?token=y']


def test_rewrite_sexbabes() -> None:
    src = 'https://cdn/videos_screenshots/abc/1920x1080/5.jpg'
    assert _rewrite_sexbabes(src) == 'https://cdn/videos_sources/abc/screenshots/5.jpg'
