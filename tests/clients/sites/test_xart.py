from __future__ import annotations

from urllib.parse import quote

import httpx
import pytest
import respx

import phoenixadult.clients.sites.xart as xart_module
from phoenixadult.clients.sites.xart import XartClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site
from tests.support import served_collections

SITE = find_site('X-Art')
assert SITE is not None

URL = 'https://x-art.com/videos/wild_ride'
GALLERY_URL = 'https://x-art.com/galleries/wild_ride'
SCENE_PAGE = """<html><body>
  <div class="row info">
    <div class="small-12 medium-12 large-12 columns">Wild Ride</div>
  </div>
  <div class="small-12 medium-12 large-12 columns info">
    <p>An exquisite scene.</p>
    <p>Set in the wilderness.</p>
  </div>
  <h2>Header One</h2>
  <h2>Header Two</h2>
  <h2>Jan 5, 2024.</h2>
  <h2><a href="https://x-art.com/models/jane">Jane Doe</a></h2>
  <img alt="thumb" src="https://cdn.example/videos/wild_ride/thumb_1.jpg" />
  <div class="video-tour"><a><img src="https://cdn.example/videos/wild_ride/tour_1.jpg" /></a></div>
</body></html>"""
ACTOR_PAGE = '<html><body><img class="info-img" src="https://cdn.example/jane.jpg" /></body></html>'


@respx.mock
async def test_search_row(monkeypatch: pytest.MonkeyPatch, no_web_search: object) -> None:
    monkeypatch.setattr(xart_module, 'web_search', no_web_search)
    url = 'https://x-art.com/search/?input_search_sm=' + quote('Wild Ride')
    html = """<html><body>
      <a href="/videos/wild_ride">
        <img src="https://cdn.example/videos/wild_ride/thumb.jpg" alt="Wild Ride" />
        <h2>Foo</h2>
        <h2>Jan 5, 2024</h2>
      </a>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await XartClient().search(results, SearchContext(title='Wild Ride', encoded=quote('Wild Ride'), search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Wild Ride'
    assert results[0].scene_url == 'https://x-art.com/videos/wild_ride'
    assert results[0].release_date == '2024-01-05'


@respx.mock
async def test_search_manual_match(monkeypatch: pytest.MonkeyPatch, no_web_search: object) -> None:
    monkeypatch.setattr(xart_module, 'web_search', no_web_search)
    respx.get('https://x-art.com/search/?input_search_sm=Sunset').mock(return_value=httpx.Response(200, text='<html></html>'))
    results: list[SearchResult] = []
    await XartClient().search(results, SearchContext(title='Sunset', encoded='Sunset', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Sunset [X-Art]'
    assert results[0].scene_url == 'https://x-art.com/videos/sunset'
    assert results[0].score == 100


@respx.mock
async def test_detail_harvest_variants(monkeypatch: pytest.MonkeyPatch, no_web_search: object) -> None:
    monkeypatch.setattr(xart_module, 'web_search', no_web_search)
    respx.get(URL).mock(return_value=httpx.Response(200, text=SCENE_PAGE))
    respx.get(GALLERY_URL).mock(return_value=httpx.Response(200, text='<html></html>'))
    respx.get('https://x-art.com/models/jane').mock(return_value=httpx.Response(200, text=ACTOR_PAGE))
    detail = await XartClient().fetch_scene_detail(URL, SITE)
    assert detail is not None
    assert detail.title == 'Wild Ride'
    assert detail.summary == 'An exquisite scene.\n\nSet in the wilderness.'
    assert detail.studio == 'X-Art'
    assert served_collections(detail) == ['X-Art']
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['Artistic', 'Glamorous']
    assert [(a.name, a.photo_url) for a in detail.actors] == [('Jane Doe', 'https://cdn.example/jane.jpg')]
    for u in (
        'https://cdn.example/videos/wild_ride/thumb_1.jpg',
        'https://cdn.example/videos/wild_ride/thumb_2.jpg',
        'https://cdn.example/videos/wild_ride/tour_1.jpg',
        'https://cdn.example/videos/wild_ride/tour_2.jpg',
    ):
        assert u in detail.art


@respx.mock
async def test_detail_fanart_supplement(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _ws(opts: object) -> list[str]:
        if getattr(opts, 'site', '') == 'xartfan.com':
            return ['https://xartfan.com/jane-wild-ride/']
        return []

    monkeypatch.setattr(xart_module, 'web_search', _ws)
    respx.get(URL).mock(return_value=httpx.Response(200, text=SCENE_PAGE))
    respx.get(GALLERY_URL).mock(return_value=httpx.Response(200, text='<html></html>'))
    respx.get('https://x-art.com/models/jane').mock(return_value=httpx.Response(200, text=ACTOR_PAGE))
    respx.get('https://xartfan.com/jane-wild-ride/').mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <header class="entry-header"><p><a>Jane Doe</a></p></header>
              <h1>Jane Doe - Wild Ride</h1>
              <div class="tiled-gallery">
                <a><img data-orig-file="https://images.xartfan.com/wild-ride/01.jpg" /></a>
                <a><img data-orig-file="https://images.xartfan.com/wild-ride/02.jpg" /></a>
              </div>
            </body></html>""",
        )
    )
    detail = await XartClient().fetch_scene_detail(URL, SITE)
    assert detail is not None
    assert 'https://xartfan.com/wild-ride/01.jpg' in detail.art
    assert 'https://xartfan.com/wild-ride/02.jpg' in detail.art
