from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext
from app.clients.sites.lustomic import LustomicClient
from app.registry import find_site

SITE = find_site('Lustomic')
assert SITE is not None

_URL = 'https://lustomic.com/video_preview_page.php?iID=42'
_PAGE = """<html><body>
  <img alt="Video Preview"><p>Some Comic</p>
  <img alt="Video Description"><div>A summary.</div>
  <p>Starring <span>Jane Doe; Mary Roe</span></p>
  <a href="/video_preview_images/1.jpg">img</a>
</body></html>"""


@respx.mock
async def test_search_reads_preview_title() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, text=_PAGE))
    results = await LustomicClient().search(SearchContext(title='42', encoded='42', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Some Comic'


@respx.mock
async def test_detail_cast_and_images() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, text=_PAGE))
    detail = await LustomicClient().fetch_scene_detail(f'{_URL}|2024-01-05', SITE)
    assert detail is not None
    assert detail.title == 'Some Comic'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Lustomic'
    assert detail.release_date == '2024-01-05'
    assert [a.name for a in detail.actors] == ['Jane Doe', 'Mary Roe']
    assert detail.raw_image_urls == ['/video_preview_images/1.jpg']
