from __future__ import annotations

import httpx
import pytest
import respx

import app.clients.networks.nvg as nvg_mod
from app.clients.base import SearchContext
from app.clients.networks.nvg import NVGClient
from app.registry import find_site

SITE = find_site('Net Video Girls')
assert SITE is not None

_PAGE_DATA = {
    'result': {
        'data': {
            'allMysqlTourStats': {
                'edges': [
                    {
                        'node': {
                            'tour_thumbs': {
                                'updates': {'mysqlId': 123, 'short_title': 'Cool Scene', 'release_date': '2021-03-04'},
                                'localFile': {'childImageSharp': {'fluid': {'src': '/img/c.jpg'}}},
                            }
                        }
                    }
                ]
            }
        }
    }
}


def _ctx(title: str = 'jane doe', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search_fallback_to_page_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(nvg_mod, 'web_search_available', lambda: False)
    respx.get(nvg_mod._PAGE_DATA_URL).mock(return_value=httpx.Response(200, json=_PAGE_DATA))
    results = await NVGClient().search(_ctx(scene_id='123'))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].score == 100


@respx.mock
async def test_detail_from_id() -> None:
    respx.get(nvg_mod._PAGE_DATA_URL).mock(return_value=httpx.Response(200, json=_PAGE_DATA))
    detail = await NVGClient().fetch_scene_detail('123|2021-03-04|Jane Doe AND John Smith', SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.studio == 'NVG Network'
    assert detail.tagline == 'Net Video Girls'
    assert detail.release_date == '2021-03-04'
    assert [a.name for a in detail.actors] == ['Jane Doe', 'John Smith']  # split on " AND "
    assert detail.raw_image_urls == ['https://netvideogirls.net/img/c.jpg']  # fluid src, base-prefixed


@respx.mock
async def test_detail_url_prefers_page_data_poster() -> None:
    # legacy merge: URL-resolved scene still prefers the page-data fluid src when mysqlId matches
    scene_url = 'https://netvideogirls.net/scene-x/'
    respx.get(scene_url).mock(
        return_value=httpx.Response(
            200,
            text='<html><head><title>Cool Scene | NVG</title></head><body><div class="the-content"><p>A summary.</p></div><video poster="https://cdn/onpage.jpg"></video></body></html>',
        )
    )
    respx.get(nvg_mod._PAGE_DATA_URL).mock(return_value=httpx.Response(200, json=_PAGE_DATA))
    detail = await NVGClient().fetch_scene_detail(f'{scene_url}|2021-03-04|Jane Doe|123', SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.scene_url == scene_url
    # page-data fluid src wins over the on-page <video poster> (legacy merge)
    assert detail.raw_image_urls == ['https://netvideogirls.net/img/c.jpg']
