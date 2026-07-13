from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.networks.badoinkvr import BadoinkVrClient, __testing__
from app.registry import find_site

SITE = find_site('BaDoinkVR')
COSPLAY = find_site('VRCosplayX')
assert SITE is not None and COSPLAY is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '%20'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search_page() -> None:
    url = 'https://badoinkvr.com/vrpornvideos/search/cool%20scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<div class="tile-grid-item">
              <a class="video-card-title" title="Cool Scene" href="/vrpornvideo/77/cool-scene"></a>
              <span class="video-card-upload-date" content="2021-03-04"></span>
            </div>""",
        )
    )
    results: list[SearchResult] = []
    await BadoinkVrClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://badoinkvr.com/vrpornvideo/77/cool-scene'


@respx.mock
async def test_search_direct_scene_id() -> None:
    url = 'https://badoinkvr.com/vrpornvideo/555'
    respx.get(url).mock(return_value=httpx.Response(200, text='<h1 class="video-title">Cool Scene</h1><img class="video-image" src="https://cdn/t.jpg?x=1" />'))
    results: list[SearchResult] = []
    await BadoinkVrClient().search(results, _ctx(scene_id='555'))
    assert len(results) == 1
    assert results[0].scene_url == url
    assert results[0].score == 100
    assert results[0].thumb_url == 'https://cdn/t.jpg?x=1'


@respx.mock
async def test_detail_fields() -> None:
    url = 'https://badoinkvr.com/vrpornvideo/77'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1 class="video-title">Cool Scene</h1>
              <p class="video-description">A summary.</p>
              <p itemprop="uploadDate" content="2021-03-04T00:00:00Z"></p>
              <a class="video-tag">VR</a><a class="video-tag">180</a>
              <a class="video-actor-link" href="/girl/jane">Jane Doe</a>
              <img class="video-image" src="https://cdn/main.jpg?token=abc" />
              <div class="gallery-item" data-big-image="https://cdn/g/base_1.jpg?v=9"></div>
              <span class="gallery-zip-info">3 photos</span>
            </body></html>""",
        )
    )
    respx.get('https://badoinkvr.com/girl/jane').mock(
        return_value=httpx.Response(200, text='<img class="girl-details-photo" src="https://cdn/jane.jpg?sig=z" />')
    )
    detail = await BadoinkVrClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'BaDoink VR'
    assert detail.tagline == 'BaDoinkVR'
    assert detail.collections == ['BaDoinkVR']
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['VR', '180']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].gender == 'female'
    assert detail.actors[0].photo_url == 'https://cdn/jane.jpg?sig=z'
    assert detail.raw_image_urls == [
        'https://cdn/main.jpg?token=abc',
        'https://cdn/g/base_1.jpg',
        'https://cdn/g/base_2.jpg',
        'https://cdn/g/base_3.jpg',
        'https://cdn/g/base_4.jpg',
    ]


def test_mangle() -> None:
    mangle = __testing__['mangle']
    assert mangle('Cool Scene a Parody 180') == 'Cool Scene'
    assert mangle('Some Parody Title') == 'Some  Title'
