from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.networks.unzipvr import UnzipVRClient
from app.registry import find_site

SITE = find_site('VR Conk')
assert SITE is not None
_BASE = 'https://content.vrconk.com'


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search() -> None:
    body = {'data': {'videos': [{'title': 'Cool Scene', 'slug': 'cool-scene'}]}}
    respx.get(f'{_BASE}/api/content/v1/search/cool%20scene').mock(return_value=httpx.Response(200, json=body))
    results: list[SearchResult] = []
    await UnzipVRClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert UnzipVRClient().decode(results[0].cur_id) == 'cool-scene'


@respx.mock
async def test_detail() -> None:
    item = {
        'title': 'Cool Scene',
        'description': '<p>A <b>summary</b>.</p>',
        'publishedAt': 1614816000,
        'categories': [{'name': 'VR'}],
        'models': [{'title': 'Jane Doe', 'featuredImage': {'permalink': '/media/jane.jpg'}}],
        'sliderImage': {'permalink': '/media/slider.jpg'},
        'poster': {'permalink': '/media/poster.jpg'},
        'galleryImages': [{'permalink': '/media/g1.jpg'}],
    }
    respx.get(f'{_BASE}/api/content/v1/videos/cool-scene').mock(return_value=httpx.Response(200, json={'data': {'item': item}}))
    detail = await UnzipVRClient().fetch_scene_detail('cool-scene', SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Unzip VR'
    assert detail.tagline == 'VR Conk'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['VR']
    assert detail.actors is not None and detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == f'{_BASE}/media/jane.jpg'
    assert detail.actors[0].gender == 'female'
    assert detail.art == [f'{_BASE}/media/slider.jpg', f'{_BASE}/media/poster.jpg', f'{_BASE}/media/g1.jpg']
