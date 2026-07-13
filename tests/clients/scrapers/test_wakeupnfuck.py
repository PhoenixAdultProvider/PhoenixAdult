from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites.wakeupnfuck import WakeUpNFuckClient
from app.registry import find_site

SITE = find_site('WakeUpNFuck')
assert SITE is not None


@respx.mock
async def test_search_per_row_actors() -> None:
    url = 'https://www.wakeupnfuck.com/search?query=wild'
    html = """<html><body>
      <a class="scene item light_background" href="/scene/a"><h3>Wild A</h3><p class="sub">Jane Doe</p></a>
      <a class="scene item light_background" href="/scene/b"><h3>Wild B</h3><p class="sub">Mary Roe</p></a>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await WakeUpNFuckClient().search(results, SearchContext(title='wild', encoded='wild', search_site=SITE.name, site_info=SITE))
    assert len(results) == 2
    assert results[0].title == 'Wild A [Jane Doe]'
    assert results[1].title == 'Wild B [Mary Roe]'


@respx.mock
async def test_detail_publish_date_split() -> None:
    url = 'https://www.wakeupnfuck.com/scene/wild'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <div class="block"><h2>wild scene</h2></div>
              <div class="description">Sample text. Publish Date : 5 January 2024</div>
              <div class="tags"><a>Hardcore</a><a>POV</a></div>
              <div class="starring">
                <a class="item"><img src="https://cdn.wunf/jane.jpg" /><p>Jane Doe</p></a>
                <a class="item"><img src="https://cdn.wunf/mary.jpg" /><p>Mary Roe</p></a>
              </div>
              <video class="player_video" poster="https://cdn.wunf/poster.jpg"></video>
            </body></html>""",
        )
    )
    detail = await WakeUpNFuckClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'wild scene'
    assert detail.studio == 'WakeUpNFuck'
    assert detail.tagline is None
    assert detail.collections == ['WakeUpNFuck']
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['Hardcore', 'POV']
    assert [(a.name, a.photo_url) for a in detail.actors] == [
        ('Jane Doe', 'https://cdn.wunf/jane.jpg'),
        ('Mary Roe', 'https://cdn.wunf/mary.jpg'),
    ]
    assert detail.raw_image_urls == ['https://cdn.wunf/poster.jpg']


@respx.mock
async def test_detail_inline_script_image_fallback() -> None:
    url = 'https://www.wakeupnfuck.com/scene/script'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <div class="block"><h2>Script Scene</h2></div>
              <div class="description">Publish Date : 12 March 2024</div>
              <script>var player = { image: "https://cdn.wunf/inline.jpg", other: "x" };</script>
            </body></html>""",
        )
    )
    detail = await WakeUpNFuckClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.raw_image_urls == ['https://cdn.wunf/inline.jpg']
