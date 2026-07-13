from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.networks.cherrypimps import CherryPimpsClient
from app.registry import find_site

SITE = find_site('Cherry Pimps')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '%20'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search_two_pages() -> None:
    page1 = """<div class="item-updates"><div class="item-update">
      <p class="text-thumb"><a href="/scene/1/cool-scene">Cool Scene</a></p>
      <span class="date">HD | Mar 4, 2021</span>
    </div></div>"""
    respx.get('https://www.cherrypimps.com/search.php?query=cool+scene&page=1').mock(return_value=httpx.Response(200, text=page1))
    respx.get('https://www.cherrypimps.com/search.php?query=cool+scene&page=2').mock(return_value=httpx.Response(200, text='<div class="item-updates"></div>'))
    results: list[SearchResult] = []
    await CherryPimpsClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://www.cherrypimps.com/scene/1/cool-scene'
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_detail() -> None:
    url = 'https://www.cherrypimps.com/scene/1/cool-scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <div class="trailer-block_title">Cool Scene</div>
              <div class="info-block"><p class="text">A summary.</p>
                <a>Anal</a><a>Gonzo</a>
                <div class="info-block_data"><a><img src0_1x="https://cdn/a.jpg" />Jane Doe</a><a>John Smith</a></div>
              </div>
              <div class="info-block_data"><p class="text">Added: Mar 4, 2021 | 12:00</p></div>
              <img class="update_thumb" src="https://cdn/t1.jpg" />
            </body></html>""",
        )
    )
    detail = await CherryPimpsClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Cherry Pimps'
    assert detail.tagline == 'Cherry Pimps'
    assert detail.release_date == '2021-03-04'
    assert 'Anal' in detail.genres and 'Gonzo' in detail.genres
    assert [a.name for a in detail.actors] == ['Jane Doe', 'John Smith']
    assert detail.actors[0].photo_url == 'https://cdn/a.jpg'
    assert detail.raw_image_urls == ['https://cdn/t1.jpg']
