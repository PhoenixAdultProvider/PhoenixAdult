from __future__ import annotations

import httpx
import pytest
import respx

import phoenixadult.clients.networks.evolvedfights as ef_mod
from phoenixadult.clients import base as client_base
from phoenixadult.models.scrape import SearchResult
from phoenixadult.registry import find_site
from tests.support import search_context


async def _no_web_search(*_a: object, **_k: object) -> list[str]:
    return []


SITE = find_site('Evolved Fights')
assert SITE is not None


@respx.mock
async def test_search_direct_guess(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_base, 'web_search_urls', _no_web_search)
    url = 'https://evolvedfights.com/cool-scene.html'
    respx.get(url).mock(return_value=httpx.Response(200, text='<title>Cool Scene</title><span class="update_date">03/04/2021</span>'))
    results: list[SearchResult] = []
    await ef_mod.EvolvedFightsClient().search(results, search_context(SITE, 'cool scene', search_date='2021-03-04', space='%20'))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == url
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_detail() -> None:
    url = 'https://evolvedfights.com/cool-scene.html'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><head><title>Cool Scene</title></head><body>
              <span class="latest_update_description">A summary.</span>
              <span class="update_date">03/04/2021</span>
              <span class="tour_update_tags"><a>Wrestling</a><a>Mixed</a></span>
              <div class="update_block_info model_update_block_info"><span class="tour_update_models"><a href="/models/jane.html">Jane Doe</a></span></div>
              <span class="model_update_thumb"><img src0_4x="/img/scene-0-4x.jpg" /></span>
            </body></html>""",
        )
    )
    respx.get('https://evolvedfights.com/models/jane.html').mock(
        return_value=httpx.Response(200, text='<img class="model_bio_thumb stdimage thumbs target" src0_3x="/p/jane.jpg" />')
    )
    detail = await ef_mod.EvolvedFightsClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Evolved Fights Network'
    assert detail.tagline == 'Evolved Fights'
    assert detail.collections == ['Evolved Fights Network']
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Wrestling', 'Mixed']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://evolvedfights.com/p/jane.jpg'
    assert detail.art == ['https://evolvedfights.com/img/scene-0-4x.jpg', 'https://evolvedfights.com/img/scene-1-4x.jpg']
