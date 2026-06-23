from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext
from app.clients.sites.woodmancastingx import WoodmanCastingXClient
from app.registry import find_site

SITE = find_site('WoodmanCastingX')
assert SITE is not None


@respx.mock
async def test_search_relative_only() -> None:
    url = 'https://www.woodmancastingx.com/search?query=wild'
    html = """<html><body>
      <div class="items">
        <a class="scene" href="/scene/wild"><img alt="Wild Scene" /></a>
        <a class="scene" href="https://elsewhere.com/x"><img alt="Skipped Absolute" /></a>
      </div>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results = await WoodmanCastingXClient().search(SearchContext(title='wild', encoded='wild', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].scene_url == 'https://www.woodmancastingx.com/scene/wild'
    assert results[0].title == 'Wild Scene'


@respx.mock
async def test_detail() -> None:
    url = 'https://www.woodmancastingx.com/scene/wild'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1>wild scene</h1>
              <p class="description">A    blurb
                with     extra    spaces.</p>
              <div><span>Published</span>: January 5, 2024</div>
              <div class="tags"><a>Anal</a><a>Hardcore</a></div>
              <div class="block_girls_videos">
                <a class="girl_item">
                  <span class="name">Jane Doe</span>
                  <img src="https://cdn.wcx/jane.jpg" />
                </a>
              </div>
              <video class="player_video" poster="https://cdn.wcx/poster.jpg"></video>
            </body></html>""",
        )
    )
    detail = await WoodmanCastingXClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'wild scene'
    assert detail.summary == 'A blurb with extra spaces.'
    assert detail.studio == 'Woodman Casting X'
    assert detail.tagline == 'WoodmanCastingX'
    assert detail.collections == ['WoodmanCastingX']
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['Anal', 'Hardcore']
    assert [(a.name, a.photo_url) for a in detail.actors] == [('Jane Doe', 'https://cdn.wcx/jane.jpg')]
    assert detail.raw_image_urls == ['https://cdn.wcx/poster.jpg']


@respx.mock
async def test_detail_breadcrumb_actress_fallback() -> None:
    url = 'https://www.woodmancastingx.com/scene/breadcrumb'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text='<html><body><h1>Breadcrumb Scene</h1><div id="breadcrumb"><span class="crumb">Sara Sun - Casting</span></div></body></html>',
        )
    )
    detail = await WoodmanCastingXClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert [a.name for a in detail.actors] == ['Sara Sun']
