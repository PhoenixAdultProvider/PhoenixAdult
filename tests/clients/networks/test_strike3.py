from __future__ import annotations

import httpx
import pytest
import respx

import phoenixadult.clients.networks.strike3 as s3
from phoenixadult.clients.networks.strike3 import Strike3Client
from phoenixadult.models.scrape import SearchResult
from phoenixadult.registry import find_site
from tests.support import search_context

SITE = find_site('Tushy')
assert SITE is not None
_ENDPOINT = 'https://www.tushy.com/graphql'


@pytest.fixture(autouse=True)
def _no_pacing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(s3, '_PACE_SECONDS', 0.0)


@respx.mock
async def test_search_text() -> None:
    body = {'data': {'searchVideos': {'edges': [{'node': {'videoId': '99', 'title': 'Cool Scene', 'releaseDate': '2021-03-04', 'slug': 'cool-scene'}}]}}}
    respx.post(_ENDPOINT).mock(return_value=httpx.Response(200, json=body))
    results: list[SearchResult] = []
    await Strike3Client().search(results, search_context(SITE, 'cool scene'))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert Strike3Client().decode(results[0].cur_id) == 'cool-scene'
    assert results[0].display_date == '2021-03-04'
    assert b'query getSearchResults($query: String!, $site: Site!' in respx.calls.last.request.content


@respx.mock
async def test_search_by_id() -> None:
    body = {'data': {'findOneVideo': {'videoId': '12345', 'title': 'Cool Scene', 'releaseDate': '2021-03-04', 'slug': 'cool-scene'}}}
    respx.post(_ENDPOINT).mock(return_value=httpx.Response(200, json=body))
    results: list[SearchResult] = []
    await Strike3Client().search(results, search_context(SITE, 'cool scene', scene_id='12345'))
    assert len(results) == 1
    assert results[0].score == 100


@respx.mock
async def test_search_goes_straight_through_impersonate(monkeypatch: pytest.MonkeyPatch) -> None:
    import json as _json

    from phoenixadult.utils.http.bypass_types import BypassRequest, BypassResponse
    from phoenixadult.utils.http.impersonate import impersonate_backend

    direct = respx.post(_ENDPOINT).mock(return_value=httpx.Response(403, html='<html>Attention Required! | Cloudflare</html>'))
    gql = {'data': {'searchVideos': {'edges': [{'node': {'videoId': '7', 'title': 'Bypassed', 'releaseDate': '2022-01-01', 'slug': 'bypassed'}}]}}}

    async def impersonated(req: BypassRequest) -> BypassResponse:
        return BypassResponse(status=200, body=_json.dumps(gql))

    monkeypatch.setattr(impersonate_backend, 'request', impersonated)
    results: list[SearchResult] = []
    await Strike3Client().search(results, search_context(SITE, title='x'))
    assert len(results) == 1 and results[0].title == 'Bypassed'
    assert not direct.called, 'PROVIDER_BYPASS sends Strike3 straight to Impersonate'


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
    assert detail.art == ['https://cdn/c1.jpg']
