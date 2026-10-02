from __future__ import annotations

import json

import httpx
import pytest
import respx

from phoenixadult.clients.sites.clips4sale import Clips4SaleClient
from phoenixadult.models.scrape import SearchResult
from phoenixadult.registry import find_site
from tests.support import search_context

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


@respx.mock
async def test_direct_clip_search() -> None:
    url = 'https://clips4sale.com/studio/57445/99999999/'
    respx.get(url).mock(return_value=httpx.Response(200, text=_page(_CLIP)))
    results: list[SearchResult] = []
    await Clips4SaleClient().search(results, search_context(SITE, '57445 99999999'))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].score == 100
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_detail() -> None:
    url = 'https://clips4sale.com/studio/57445/99999999/'
    respx.get(url).mock(return_value=httpx.Response(200, text=_page(_CLIP)))
    detail = await Clips4SaleClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Clips4Sale'
    assert detail.tagline == 'My Studio'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['teen']
    assert detail.actors == []
    assert 'https://cdn/p.jpg' in (detail.art or [])
    assert 'http://imagecdn.clips4sale.com/accounts99/57445/clip_images/previewlg_99999999.jpg' in (detail.art or [])


@pytest.mark.parametrize(
    ('raw', 'clean'),
    [
        ('Cool Scene (HD - HD)', 'Cool Scene'),
        ('Cool Scene (1080p MP4)', 'Cool Scene'),
        ('Cool Scene 4K wmv', 'Cool Scene'),
        ('Cool Scene - standard;', 'Cool Scene'),
        ('Cool Scene.avi', 'Cool Scene'),
        ('Cool Scene (720P)', 'Cool Scene'),
        ('Cool Scene', 'Cool Scene'),
    ],
)
def test_titles_lose_their_format_and_quality_tags(raw: str, clean: str) -> None:
    from phoenixadult.clients.sites.clips4sale import _clean_title

    assert _clean_title(raw) == clean
