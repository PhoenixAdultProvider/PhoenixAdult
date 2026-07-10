from __future__ import annotations

import httpx
import pytest
import respx

import app.clients.networks.strike3 as s3
from app.clients.base import SearchContext
from app.clients.networks.strike3 import Strike3Client
from app.registry import find_site

SITE = find_site('Tushy')
assert SITE is not None
_ENDPOINT = 'https://www.tushy.com/graphql'


@pytest.fixture(autouse=True)
def _no_pacing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(s3, '_PACE_SECONDS', 0.0)


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search_text() -> None:
    body = {'data': {'searchVideos': {'edges': [{'node': {'videoId': '99', 'title': 'Cool Scene', 'releaseDate': '2021-03-04', 'slug': 'cool-scene'}}]}}}
    respx.post(_ENDPOINT).mock(return_value=httpx.Response(200, json=body))
    results = await Strike3Client().search(_ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert Strike3Client().decode(results[0].cur_id) == 'cool-scene'
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_search_by_id() -> None:
    body = {'data': {'findOneVideo': {'videoId': '12345', 'title': 'Cool Scene', 'releaseDate': '2021-03-04', 'slug': 'cool-scene'}}}
    respx.post(_ENDPOINT).mock(return_value=httpx.Response(200, json=body))
    results = await Strike3Client().search(_ctx(scene_id='12345'))
    assert len(results) == 1
    assert results[0].score == 100


@respx.mock
async def test_search_recovers_via_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    import json as _json

    monkeypatch.setenv('FLARESOLVERR_URL', 'http://localhost:8191')
    monkeypatch.setenv('BYPASS_ORDER', 'FlareSolverr')
    respx.post(_ENDPOINT).mock(return_value=httpx.Response(403, html='<html>Attention Required! | Cloudflare</html>'))
    gql = {'data': {'searchVideos': {'edges': [{'node': {'videoId': '7', 'title': 'Bypassed', 'releaseDate': '2022-01-01', 'slug': 'bypassed'}}]}}}
    envelope = {'status': 'ok', 'solution': {'url': _ENDPOINT, 'status': 200, 'response': _json.dumps(gql), 'headers': {}, 'cookies': []}}
    respx.post('http://localhost:8191/v1').mock(return_value=httpx.Response(200, json=envelope))

    results = await Strike3Client().search(_ctx(title='x'))
    assert len(results) == 1 and results[0].title == 'Bypassed'


@respx.mock
async def test_detail() -> None:
    body = {
        'data': {
            'findOneVideo': {
                'videoId': '99',
                'title': 'Cool Scene',
                'description': 'A summary.',
                'releaseDate': '2021-03-04',
                'models': [{'name': 'Jane Doe', 'images': {'listing': [{'highdpi': {'double': 'https://cdn/jane.jpg'}}]}}],
                'directors': [{'name': 'Mr Vixen'}],
                'categories': [{'name': 'Hardcore'}],
                'carousel': [{'listing': [{'highdpi': {'triple': 'https://cdn/c1.jpg'}}]}],
            }
        }
    }
    respx.post(_ENDPOINT).mock(return_value=httpx.Response(200, json=body))
    detail = await Strike3Client().fetch_scene_detail('cool-scene', SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Tushy'
    assert detail.collections == ['Tushy']
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Anal', 'Hardcore']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://cdn/jane.jpg'
    assert detail.directors is not None and detail.directors[0].name == 'Mr Vixen'
    assert detail.raw_image_urls == ['https://cdn/c1.jpg']
