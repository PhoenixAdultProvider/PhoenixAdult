from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.networks.wownetwork import WowNetworkClient
from app.registry import find_site

SITE = find_site('Wow Girls')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search() -> None:
    page1 = '<article class="thumb-block"><a href="/v/7" title="Cool Scene"></a><img src="https://cdn/t.jpg" /></article>'
    respx.get('https://wowgirlsblog.com/?s=cool+scene').mock(return_value=httpx.Response(200, text=page1))
    respx.get('https://wowgirlsblog.com/page/2/?s=cool+scene').mock(return_value=httpx.Response(200, text=''))
    respx.get('https://wowgirlsblog.com/v/7').mock(return_value=httpx.Response(200, text='<html><body></body></html>'))
    results: list[SearchResult] = []
    await WowNetworkClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://wowgirlsblog.com/v/7'
    detail = await WowNetworkClient().fetch_scene_detail(WowNetworkClient().decode(results[0].cur_id), SITE)
    assert detail is not None
    assert 'https://cdn/t.jpg' in (detail.raw_image_urls or [])


@respx.mock
async def test_detail() -> None:
    url = 'https://wowgirlsblog.com/v/7'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1 class="entry-title">Cool Scene</h1>
              <div id="video-date">Date: March 4, 2021</div>
              <div class="tags-list"><a><i class="fa fa-folder-open"></i>Teen Movies</a></div>
              <div id="video-actors"><a>Jane Doe</a></div>
              <meta property="og:image" content="https://cdn/og.jpg" />
            </body></html>""",
        )
    )
    detail = await WowNetworkClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.studio == 'WowNetwork'
    assert detail.tagline == 'Wow Girls'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Teen']
    assert detail.actors is not None and detail.actors[0].name == 'Jane Doe'
    assert detail.raw_image_urls == ['https://cdn/og.jpg']
