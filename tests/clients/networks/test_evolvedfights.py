from __future__ import annotations

import httpx
import pytest
import respx

import app.clients.networks.evolvedfights as ef_mod
from app.clients.base import SearchContext
from app.registry import find_site

SITE = find_site('Evolved Fights')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '%20'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search_direct_guess(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ef_mod, 'web_search_available', lambda: False)
    url = 'https://evolvedfights.com/cool-scene.html'
    respx.get(url).mock(return_value=httpx.Response(200, text='<title>Cool Scene</title><span class="update_date">03/04/2021</span>'))
    results = await ef_mod.EvolvedFightsClient().search(_ctx(search_date='2021-03-04'))
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
    assert detail.raw_image_urls == ['https://evolvedfights.com/img/scene-0-4x.jpg', 'https://evolvedfights.com/img/scene-1-4x.jpg']
