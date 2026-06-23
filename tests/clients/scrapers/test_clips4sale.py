from __future__ import annotations

import json

import httpx
import respx

from app.clients.base import SearchContext
from app.clients.sites.clips4sale import Clips4SaleClient
from app.registry import find_site

SITE = find_site('Clips4Sale')
assert SITE is not None

_CLIP = {
    'title': 'Cool Scene (HD mp4)',
    'dateDisplay': '03/04/21 10:00',
    'description': '<p>A summary.</p>--SCREEN SIZE 1920',
    'category_name': 'Cherry',
    'keyword_links': [{'keyword': 'Teen'}],
    'studioTitle': 'My Studio',
    'preview_screencap_image_path': 'https://cdn/p.jpg',
}


def _page(clip: dict) -> str:
    remix = {'state': {'loaderData': {'routes/($lang).studio.$id_.$clipId.$clipSlug': {'clip': clip}}}}
    return f'<html><body><script>window.__remixContext = {json.dumps(remix)};</script></body></html>'


def _ctx(title: str, **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_direct_clip_search() -> None:
    url = 'https://clips4sale.com/studio/57445/99999999/'
    respx.get(url).mock(return_value=httpx.Response(200, text=_page(_CLIP)))
    results = await Clips4SaleClient().search(_ctx('57445 99999999'))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'  # quality/filetype noise stripped
    assert results[0].score == 100
    assert results[0].display_date == '2021-03-04'  # MM/dd/yy


@respx.mock
async def test_detail() -> None:
    url = 'https://clips4sale.com/studio/57445/99999999/'
    respx.get(url).mock(return_value=httpx.Response(200, text=_page(_CLIP)))
    detail = await Clips4SaleClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'  # tags stripped, --SCREEN SIZE cut
    assert detail.studio == 'Clips4Sale'
    assert detail.tagline == 'My Studio'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['teen']  # 'cherry' removed by the 57445 rule
    assert detail.actors == []
    assert 'https://cdn/p.jpg' in (detail.raw_image_urls or [])
    assert 'http://imagecdn.clips4sale.com/accounts99/57445/clip_images/previewlg_99999999.jpg' in (detail.raw_image_urls or [])
