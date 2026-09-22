from __future__ import annotations

import httpx
import pytest
import respx

from phoenixadult.clients.sites import colette as colette_module
from phoenixadult.clients.sites.colette import ColetteClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site

SITE = find_site('Colette')
assert SITE is not None

DETAIL_HTML = """<html><body>
  <div class="row info"><div><h1>Hot Scene</h1></div></div>
  <h2>2021-10-10</h2>
  <div class="info"><p>first p</p><p>A blurb.</p></div>
  <div class="info"><h2><a href="/models/alice">Alice</a><a href="/models/bob">Bob</a><a href="/models/carol">Carol</a></h2></div>
  <div class="widescreen"><img data-interchange="[img_small, (small)], [img_med, (medium)], [https://cdn.col.com/scene.jpg, (large)]"></div>
</body></html>"""

GALLERY_HTML = """<html><body>
  <div class="gallery-item"><a><img src="https://cdn.col.com/g1.jpg"></a></div>
</body></html>"""

ACTOR_HTML = '<html><body><img class="info-img" data-interchange="[s, (small)], [m, (medium)], [https://cdn.col.com/alice.jpg, (large)]"></body></html>'


@respx.mock
async def test_search_constructed_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _no_web(*_a: object, **_k: object) -> list[str]:
        return []

    monkeypatch.setattr(colette_module, 'web_search_urls', _no_web)
    url = 'https://colette.com/videos/Hot_Scene'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    respx.get('https://colette.com/galleries/Hot_Scene').mock(return_value=httpx.Response(200, text=GALLERY_HTML))
    results: list[SearchResult] = []
    await ColetteClient().search(results, SearchContext(title='Hot Scene', encoded='', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Hot Scene'
    assert results[0].scene_url == url
    assert results[0].release_date == '2021-10-10'


@respx.mock
async def test_detail_genres_actors_images() -> None:
    url = 'https://colette.com/videos/Hot_Scene'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    respx.get('https://colette.com/galleries/Hot_Scene').mock(return_value=httpx.Response(200, text=GALLERY_HTML))
    for slug in ('alice', 'bob', 'carol'):
        respx.get(f'https://colette.com/models/{slug}').mock(return_value=httpx.Response(200, text=ACTOR_HTML))
    detail = await ColetteClient().fetch_scene_detail(f'{url}|2021-10-10', SITE)
    assert detail is not None
    assert detail.title == 'Hot Scene'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'Colette'
    assert detail.collections == ['Colette']
    assert detail.release_date == '2021-10-10'
    assert detail.genres == ['Threesome']
    assert [a.name for a in detail.actors] == ['Alice', 'Bob', 'Carol']
    assert detail.actors[0].photo_url == 'https://cdn.col.com/alice.jpg'
    assert detail.art == ['https://cdn.col.com/g1.jpg', 'https://cdn.col.com/scene.jpg']
