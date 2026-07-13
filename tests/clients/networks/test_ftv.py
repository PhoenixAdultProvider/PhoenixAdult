from __future__ import annotations

import httpx
import pytest
import respx

import app.clients.networks.ftv as ftv_mod
from app.clients.base import SearchContext, SearchResult
from app.registry import find_site

SITE = find_site('FTVGirls')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '%20'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search_direct_scene_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ftv_mod, 'web_search_available', lambda: False)
    url = 'https://www.ftvgirls.com/update/s-555.html'
    respx.get(url).mock(return_value=httpx.Response(200, text='<title>Cool Scene Released March 4, 2021!</title>'))
    results: list[SearchResult] = []
    await ftv_mod.FTVClient().search(results, _ctx(scene_id='555'))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == url


@respx.mock
async def test_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ftv_mod, 'web_search_available', lambda: False)
    url = 'https://www.ftvgirls.com/update/s-555.html'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><head><title>Cool Scene Released March 4, 2021!</title></head><body>
              <div id="Bio">A summary featuring Jane Doe here.</div>
              <div id="ModelDescription"><h1>Jane's Statistics</h1></div>
              <div id="Thumbs"><img src="/t/jane.jpg" /></div>
              <img id="Magazine" src="/img/mag.jpg" />
            </body></html>""",
        )
    )
    detail = await ftv_mod.FTVClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary featuring Jane Doe here.'
    assert detail.studio == 'First Time Videos'
    assert detail.tagline == 'FTVGirls'
    assert detail.collections == ['FTVGirls']
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Teen', 'Solo', 'Public']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://www.ftvgirls.com/t/jane.jpg'
    assert detail.raw_image_urls == ['https://www.ftvgirls.com/img/mag.jpg']


def test_photo_lookup() -> None:
    assert ftv_mod.__testing__['photo_lookup'](226) == ['cool-colors', 'shes-on-fire', 'heating-up']
    assert ftv_mod.__testing__['photo_lookup'](1573) == []
    assert ftv_mod.__testing__['photo_lookup'](999999) == ['none']
