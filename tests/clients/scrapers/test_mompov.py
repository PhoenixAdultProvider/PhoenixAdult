from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites.mompov import MomPOVClient
from app.registry import find_site

SITE = find_site('Mom POV')
assert SITE is not None

_DATE_HOLDER = '<div class="date_holder"><span>Jan<span>2024</span></span><span>05</span></div>'


@respx.mock
async def test_search_parses_entry_and_date() -> None:
    html = (
        '<div id="inner_content"><div class="entry">'
        '<div class="title_holder"><h1><a href="http://www.mompov.com/scene-1">Jane Scene</a></h1></div>'
        f'{_DATE_HOLDER}</div></div>'
    )
    respx.get('http://www.mompov.com/tour/?s=Jane').mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await MomPOVClient().search(results, SearchContext(title='Jane', encoded='Jane', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Jane Scene'
    assert results[0].scene_url == 'http://www.mompov.com/scene-1'
    assert results[0].release_date == '2024-01-05'


@respx.mock
async def test_detail_fields() -> None:
    url = 'http://www.mompov.com/scene-1'
    html = f'<html><body><a class="title">Jane Scene</a><div class="entry_content"><p>A summary.</p></div>{_DATE_HOLDER}</body></html>'
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    detail = await MomPOVClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Jane Scene'
    assert detail.studio == 'MomPOV'
    assert detail.tagline == 'Mom POV'
    assert detail.summary == 'A summary.'
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['MILF']
