from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites.melenamariarya import MelenaMariaRyaClient
from app.registry import find_site

SITE = find_site('Melena Maria Rya')
assert SITE is not None

_URL = 'https://www.melenamariarya.com/scene/77'
_SCENE = """<html><head>
  <title>Hot Scene with Anna Smith 4K - Sex Movies Featuring Melena Maria Rya</title>
  <meta name="description" content="A summary.">
</head><body></body></html>"""


@respx.mock
async def test_search_scene_id_scored_100() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, text=_SCENE))
    results: list[SearchResult] = []
    await MelenaMariaRyaClient().search(results, SearchContext(title='77', encoded='77', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].score == 100
    assert results[0].title == 'Hot Scene with Anna Smith 4K'


@respx.mock
async def test_detail_strips_4k_and_parses_costar() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, text=_SCENE))
    detail = await MelenaMariaRyaClient().fetch_scene_detail(f'{_URL}|2024-01-05', SITE)
    assert detail is not None
    assert detail.title == 'Hot Scene with Anna Smith'
    assert detail.studio == 'Melena Maria Rya'
    assert detail.summary == 'A summary.'
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['European']
    assert [(a.name, a.photo_url) for a in detail.actors] == [('Melena Maria Rya', ''), ('Anna Smith', '')]
