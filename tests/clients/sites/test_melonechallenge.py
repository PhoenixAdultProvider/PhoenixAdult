from __future__ import annotations

import httpx
import pytest
import respx

from phoenixadult.clients.sites.melonechallenge import MeloneChallengeClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site

SITE = find_site('Melone Challenge')
assert SITE is not None

_URL = 'https://melonechallenge.com/video/some-scene'
_PAGE = '<html><body><a class="dark">Melone Scene</a><figure><img src="https://cdn.example/poster.jpg"></figure></body></html>'
_DDG = f'<a class="result__a" href="//duckduckgo.com/l/?uddg={"https%3A%2F%2Fmelonechallenge.com%2Fvideo%2Fsome-scene"}&rut=x">x</a>'


@pytest.fixture(autouse=True)
def no_google(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('GOOGLE_SEARCH_API_KEY', raising=False)


async def test_detail_fields() -> None:
    with respx.mock:
        respx.get(_URL).mock(return_value=httpx.Response(200, text=_PAGE))
        detail = await MeloneChallengeClient().fetch_scene_detail(f'{_URL}|2024-01-05', SITE)
    assert detail is not None
    assert detail.title == 'Melone Scene'
    assert detail.studio == 'Melone Challenge'
    assert detail.tagline == 'Melone Challenge'
    assert detail.release_date == '2024-01-05'
    assert detail.art == ['https://cdn.example/poster.jpg']


@respx.mock
async def test_search_via_websearch() -> None:
    respx.route(method='GET', url__regex=r'duckduckgo\.com/html').mock(return_value=httpx.Response(200, text=_DDG))
    respx.get(_URL).mock(return_value=httpx.Response(200, text=_PAGE))
    results: list[SearchResult] = []
    await MeloneChallengeClient().search(results, SearchContext(title='Melone Scene', encoded='Melone%20Scene', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].scene_url == _URL
    assert results[0].title == 'Melone Scene'
