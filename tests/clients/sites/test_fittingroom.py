from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.sites.fittingroom import FittingRoomClient
from phoenixadult.registry import find_site

SITE = find_site('Fitting-Room')
assert SITE is not None

DETAIL_HTML = """<html><head>
  <title>Fitting-Room | Tight Squeeze</title>
  <meta property="video:release_date" content="2021-12-01">
  <meta property="video:tag" content="Lingerie">
  <meta property="video:tag" content="Alice Star Solo">
</head><body>
  <div><div>Description <em>A blurb.</em></div></div>
  <div><div>Series <a>Special Series</a></div></div>
  <div><div>Models <a>Alice Star</a></div></div>
  <a class="model"><div><img alt="Alice Star" src="https://cdn.fr.com/alice.jpg"></div></a>
</body></html>"""


@respx.mock
async def test_search_direct_sceneid() -> None:
    url = 'https://www.fitting-room.com/video/777/1'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    results: list[SearchResult] = []
    await FittingRoomClient().search(results, SearchContext(title='777 tight squeeze', encoded='', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Tight Squeeze'
    assert results[0].scene_url == url
    assert results[0].score == 90


@respx.mock
async def test_detail_fields_collection_genres_images() -> None:
    url = 'https://www.fitting-room.com/video/777/1'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    detail = await FittingRoomClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Tight Squeeze'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'Fitting-Room'
    assert detail.collections == ['Fitting-Room', 'Special Series']
    assert detail.release_date == '2021-12-01'
    assert detail.genres == ['lingerie', 'solo', 'Fitting Room']
    assert [a.name for a in detail.actors] == ['Alice Star']
    assert detail.art[0] == 'https://www.fitting-room.com/contents/videos_screenshots/0/777/preview.jpg'
    assert len(detail.art) == 5
