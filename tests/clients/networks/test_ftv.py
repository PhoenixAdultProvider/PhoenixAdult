from __future__ import annotations

import httpx
import pytest
import respx

import phoenixadult.clients.networks.ftv as ftv_mod
from phoenixadult.models.scrape import SearchResult
from phoenixadult.registry import find_site
from tests.support import search_context, served_collections


async def _no_web_search(*_a: object, **_k: object) -> list[str]:
    return []


SITE = find_site('FTVGirls')
assert SITE is not None


@respx.mock
async def test_search_direct_scene_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ftv_mod, 'web_search_urls', _no_web_search)
    url = 'https://www.ftvgirls.com/update/s-555.html'
    respx.get(url).mock(return_value=httpx.Response(200, text='<title>Cool Scene Released March 4, 2021!</title>'))
    results: list[SearchResult] = []
    await ftv_mod.FTVClient().search(results, search_context(SITE, 'cool scene', scene_id='555', space='%20'))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == url


@respx.mock
async def test_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ftv_mod, 'web_search_urls', _no_web_search)
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
    assert served_collections(detail) == ['FTVGirls']
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Teen', 'Solo', 'Public']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://www.ftvgirls.com/t/jane.jpg'
    assert detail.art == ['https://www.ftvgirls.com/img/mag.jpg']


def test_photo_lookup() -> None:
    assert ftv_mod.__testing__['photo_lookup'](226) == ['cool-colors', 'shes-on-fire', 'heating-up']
    assert ftv_mod.__testing__['photo_lookup'](1573) == []
    assert ftv_mod.__testing__['photo_lookup'](999999) == ['none']
