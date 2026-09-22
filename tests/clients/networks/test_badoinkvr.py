from __future__ import annotations

import httpx
import pytest
import respx

import phoenixadult.clients.networks.badoinkvr as badoinkvr_module
from phoenixadult.clients.networks.badoinkvr import BadoinkVrClient, __testing__
from phoenixadult.models.scrape import SearchResult
from phoenixadult.registry import find_site
from tests.support import search_context, served_collections

SITE = find_site('BaDoinkVR')
COSPLAY = find_site('VRCosplayX')
assert SITE is not None and COSPLAY is not None


def _mock_dims(monkeypatch: pytest.MonkeyPatch, existing: set[str]) -> None:
    async def fake_dims(url: str, referers: object = None, cookies: object = None) -> dict[str, int] | None:
        return {'width': 1500, 'height': 1000} if url in existing else None

    monkeypatch.setattr(badoinkvr_module, 'fetch_dimensions', fake_dims)


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
    await BadoinkVrClient().search(results, search_context(SITE, 'cool scene', space='%20'))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://badoinkvr.com/vrpornvideo/77/cool-scene'


@respx.mock
async def test_search_direct_scene_id() -> None:
    url = 'https://badoinkvr.com/vrpornvideo/555'
    respx.get(url).mock(return_value=httpx.Response(200, text='<h1 class="video-title">Cool Scene</h1><img class="video-image" src="https://cdn/t.jpg?x=1" />'))
    results: list[SearchResult] = []
    await BadoinkVrClient().search(results, search_context(SITE, 'cool scene', scene_id='555', space='%20'))
    assert len(results) == 1
    assert results[0].scene_url == url
    assert results[0].score == 100
    assert results[0].thumb_url == 'https://cdn/t.jpg?x=1'


@respx.mock
async def test_detail_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_dims(monkeypatch, {'https://cdn/g/base_1.jpg', 'https://cdn/g/base_2.jpg', 'https://cdn/g/base_3.jpg'})
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
    assert detail.tagline == ''
    assert served_collections(detail) == ['BaDoink VR']
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['VR', '180']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].gender == 'female'
    assert detail.actors[0].photo_url == 'https://cdn/jane.jpg?sig=z'
    assert detail.art == [
        'https://cdn/main.jpg?token=abc',
        'https://cdn/g/base_1.jpg?v=9',
        'https://cdn/g/base_1.jpg',
        'https://cdn/g/base_2.jpg',
        'https://cdn/g/base_3.jpg',
    ]


@respx.mock
async def test_summary_reads_the_container_when_the_description_tag_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_dims(monkeypatch, set())
    url = 'https://vrcosplayx.com/cosplaypornvideo/77'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1 class="video-title">Cool Scene</h1>
              <div class="video-description-container">
                <p class="video-description" itemprop="description" content="&lt;p&gt;A summary.&lt;/p&gt;"></p>
                <p>A <a href="/x">summary</a>.</p>
                <p></p>
              </div>
            </body></html>""",
        )
    )
    detail = await BadoinkVrClient().fetch_scene_detail(url, COSPLAY)
    assert detail is not None
    assert detail.summary == 'A summary.'


@respx.mock
async def test_detail_at_style_gallery_iterates_middle_index(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_dims(monkeypatch, {'https://img2.badoink.com/content/scenes/323737/1_2_27@1500-1x.jpg'})
    url = 'https://badoinkvr.com/vrpornvideo/323737'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1 class="video-title">Cool Scene</h1>
              <div class="gallery-item" data-big-image="https://img2.badoink.com/content/scenes/323737/1_1_27@1500-1x.jpg"></div>
              <span class="gallery-zip-info">2 photos</span>
            </body></html>""",
        )
    )
    detail = await BadoinkVrClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.art == [
        'https://img2.badoink.com/content/scenes/323737/1_1_27@1500-1x.jpg',
        'https://img2.badoink.com/content/scenes/323737/1_2_27@1500-1x.jpg',
    ]


@respx.mock
async def test_detail_mixed_family_gallery_recovers_slug_tail(monkeypatch: pytest.MonkeyPatch) -> None:
    shots = 'https://img2.badoink.com/content/screenshots/1/b/b/6/9'
    scenes = 'https://img2.badoink.com/content/scenes/323582'
    _mock_dims(monkeypatch, {f'{shots}/323582_1_2.jpg', f'{scenes}/cream-of-legends-323582.jpg', f'{scenes}/cream-of-legends-323582_1.jpg'})
    url = 'https://vrcosplayx.com/cosplaypornvideo/cream_of_legends-323582/'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text=f"""<html><body>
              <h1 class="video-title">Cream of Legends</h1>
              <div class="gallery-item" data-big-image="{shots}/323582_1_1.jpg"></div>
              <span class="gallery-zip-info">4 photos</span>
            </body></html>""",
        )
    )
    detail = await BadoinkVrClient().fetch_scene_detail(url, COSPLAY)
    assert detail is not None
    assert detail.art == [
        f'{shots}/323582_1_1.jpg',
        f'{shots}/323582_1_2.jpg',
        f'{scenes}/cream-of-legends-323582.jpg',
        f'{scenes}/cream-of-legends-323582_1.jpg',
    ]


def test_mangle() -> None:
    mangle = __testing__['mangle']
    assert mangle('Cool Scene a Parody 180') == 'Cool Scene'
    assert mangle('Some Parody Title') == 'Some  Title'
