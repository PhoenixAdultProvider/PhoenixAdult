from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites.cumlouder import CumLouderClient
from app.registry import find_site

SITE = find_site('CumLouder')
assert SITE is not None


@respx.mock
async def test_search_parses_medida_cards() -> None:
    url = 'https://cumlouder.com/search?q=%22wild%20scene%22'
    html = """<html><body>
      <div class="listado-escenas listado-busqueda"><div class="medida">
        <a href="/scene/wild"><h2>Wild Scene</h2></a>
      </div></div>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await CumLouderClient().search(results, SearchContext(title='wild scene', encoded='wild%20scene', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Wild Scene'
    assert results[0].scene_url == 'https://cumlouder.com/scene/wild'


@respx.mock
async def test_detail_fields_genres_actors_images() -> None:
    url = 'https://cumlouder.com/scene/wild'
    html = """<html><body>
      <h1>Wild Scene</h1>
      <div id="content-more-less"><p>A blurb.</p></div>
      <div class="added">Added 3 days ago</div>
      <ul class="tags"><li><a>POV</a></li><li><a>HD</a></li></ul>
      <a class="pornstar-link">Alice</a>
      <a class="pornstar-link">Bob</a>
      <a class="pornstar-link">Carol</a>
      <div class="box-video box-video-html5"><video lazy="https://cdn.cl.com/poster.jpg"></video></div>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    detail = await CumLouderClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Wild Scene'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'CumLouder'
    assert detail.tagline == 'CumLouder'
    assert detail.collections == ['CumLouder']
    assert detail.genres == ['POV', 'HD', 'Threesome']
    assert [a.name for a in detail.actors] == ['Alice', 'Bob', 'Carol']
    assert detail.raw_image_urls == ['https://cdn.cl.com/poster.jpg']
    expected = (datetime.now(UTC) - timedelta(days=3)).strftime('%Y-%m-%d')
    assert detail.release_date == expected
