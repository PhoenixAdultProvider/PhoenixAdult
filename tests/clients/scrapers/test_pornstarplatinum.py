from __future__ import annotations

import json

import httpx
import respx

from app.clients.base import SearchContext
from app.clients.sites.pornstarplatinum import PornstarPlatinumClient
from app.registry import find_site
from app.utils.helpers.helpers import pack_cur_id

SITE = find_site('Pornstar Platinum')
assert SITE is not None


@respx.mock
async def test_search_cards() -> None:
    url = 'https://www.pornstarplatinum.com/tour/index.php?search=platinum'
    html = """<html><body>
      <div class="item no-nth ">
        <div class="item-header"><a><img rel="https://cdn.psp.com/poster.jpg"></a></div>
        <div class="item-content">
          <h3><a href="/scene/platinum">Platinum Scene</a></h3>
          <div style="overflow:hidden"><span class="left content-date">2021-09-09</span><span class="marker left">Alice</span></div>
        </div>
      </div>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results = await PornstarPlatinumClient().search(SearchContext(title='platinum', encoded='platinum', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Platinum Scene'
    assert results[0].scene_url == 'https://www.pornstarplatinum.com/scene/platinum'
    assert results[0].release_date == '2021-09-09'


@respx.mock
async def test_detail_from_packed_curid() -> None:
    scene_url = 'https://www.pornstarplatinum.com/scene/platinum'
    detail_html = """<html><body>
      <div class="panel-content"><p>A blurb.</p></div>
      <div class="tagcloud"><a>Anal</a><a>MILF</a></div>
    </body></html>"""
    respx.get(scene_url).mock(return_value=httpx.Response(200, text=detail_html))
    packed = json.dumps(
        {'url': scene_url, 'title': 'Platinum Scene', 'releaseDate': '2021-09-09', 'poster': 'https://cdn.psp.com/poster.jpg', 'actor': 'Alice'}
    )
    cur_id = pack_cur_id([packed])
    detail = await PornstarPlatinumClient().fetch_scene_detail(PornstarPlatinumClient().decode(cur_id), SITE)
    assert detail is not None
    assert detail.title == 'Platinum Scene'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'Pornstar Platinum'
    assert detail.release_date == '2021-09-09'
    assert detail.genres == ['Anal', 'MILF']
    assert [a.name for a in detail.actors] == ['Alice']
    assert detail.raw_image_urls == ['https://cdn.psp.com/poster.jpg']
