from __future__ import annotations

import httpx
import pytest
import respx

import app.clients.networks.dirtyharddrive as dhd_mod
from app.clients.base import SearchContext
from app.registry import find_site

SITE = find_site('Dirty Hard Drive')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '%20'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dhd_mod, 'web_search_available', lambda: True)

    async def fake_filtered(_opts: object, url_contains: str | None = None, url_ends_with: str | None = None) -> list[str]:
        return ['https://dirtyharddrive.com/tour1/cool-scene.html']

    monkeypatch.setattr(dhd_mod, 'web_search_filtered', fake_filtered)
    respx.get('https://dirtyharddrive.com/tour1/cool-scene.html').mock(return_value=httpx.Response(200, text='<h1>Cool Scene</h1>'))
    results = await dhd_mod.DirtyHardDriveClient().search(_ctx(search_date='2021-03-04'))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://dirtyharddrive.com/tour1/cool-scene.html'


@respx.mock
async def test_search_no_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dhd_mod, 'web_search_available', lambda: False)
    assert await dhd_mod.DirtyHardDriveClient().search(_ctx()) == []


@respx.mock
async def test_detail_with_playlist_poster() -> None:
    url = 'https://dirtyharddrive.com/tour1/cool-scene.html'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1>Cool Scene</h1>
              <div id="video-page-desc">A summary.</div>
              <div id="video-specs"><span>30 min</span><span><a href="/pornstar_jane_doe.html">Jane Doe</a></span></div>
              <script>jwplayer().setup({'playlistfile': '/media/cool/playlist.xml', 'image': '/media/cool/bookend.jpg'});</script>
            </body></html>""",
        )
    )
    respx.get('https://dirtyharddrive.com/pornstar_jane_doe.html').mock(
        return_value=httpx.Response(200, text='<div id="global-model-img"><img src="/p/jane.jpg" /></div>')
    )
    respx.get('https://dirtyharddrive.com/media/cool/playlist.xml').mock(
        return_value=httpx.Response(
            200, text='<rss><channel><item><media:group><media:thumbnail url="https://cdn/thumb.jpg" /></media:group></item></channel></rss>'
        )
    )
    detail = await dhd_mod.DirtyHardDriveClient().fetch_scene_detail(f'{url}|2021-03-04', SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Dirty Hard Drive'
    assert detail.tagline is None  # single brand (site name == studio)
    assert detail.collections == ['Dirty Hard Drive']
    assert detail.release_date == '2021-03-04'
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://dirtyharddrive.com/p/jane.jpg'
    assert detail.raw_image_urls == ['https://cdn/thumb.jpg']


@respx.mock
async def test_detail_bookend_fallback() -> None:
    url = 'https://dirtyharddrive.com/tour1/x.html'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body><h1>X</h1>
              <div id="video-specs"><span><a href="/pornstar_x.html"></a></span></div>
              <script>var c = {'image': '/media/x/bookend.jpg'};</script>
            </body></html>""",
        )
    )
    respx.get('https://dirtyharddrive.com/pornstar_x.html').mock(return_value=httpx.Response(200, text='<div></div>'))
    detail = await dhd_mod.DirtyHardDriveClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.actors[0].name == 'X'  # derived from slug pornstar_x.html
    assert detail.raw_image_urls == ['https://dirtyharddrive.com/media/x/bookend.jpg']
