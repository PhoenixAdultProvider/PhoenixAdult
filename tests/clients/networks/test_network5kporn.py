from __future__ import annotations

import httpx
import pytest
import respx

from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.networks.network5kporn import Network5KPClient
from phoenixadult.registry import find_site

SITE = find_site('5Kporn')
assert SITE is not None


@pytest.fixture(autouse=True)
def _strip_actors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('SEARCH_STRIP_ACTORS', SITE.name)


def _ctx(title: str = 'Jane Doe Cool Scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search_json_html() -> None:
    url = 'https://www.5kporn.com/episodes/search?search=Jane%20Doe'
    inner = '<div class="col ep"><div class="ep-body"><a href="https://www.5kporn.com/video/5KP1"></a><h3 class="ep-title">Cool Scene</h3></div></div>'
    respx.get(url).mock(return_value=httpx.Response(200, json={'html': inner}))
    results: list[SearchResult] = []
    await Network5KPClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://www.5kporn.com/video/5KP1'


@respx.mock
async def test_detail() -> None:
    scene_url = 'https://www.5kporn.com/video/5KT9'
    respx.get(scene_url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><head><title>Cool Scene | 5Kteens</title></head><body>
              <div class="video-summary"><p class="lead">x</p><p>A summary.</p></div>
              <h5>Published: March 4, 2021</h5>
              <h5>Starring <a href="https://www.5kporn.com/model/jane">Jane Doe</a></h5>
              <div class="gal"><img src="https://cdn/g1.jpg" /></div>
            </body></html>""",
        )
    )
    respx.get('https://www.5kporn.com/model/jane').mock(return_value=httpx.Response(200, text='<img class="model-image" src="https://cdn/jane.jpg" />'))
    respx.get('https://www.5kporn.com/video/5KT9/photoset?page=1').mock(
        return_value=httpx.Response(200, text='<img class="card-img-top" src="https://cdn/p1.jpg" /><img class="card-img-top" src="https://cdn/full-x.jpg" />')
    )
    respx.get('https://www.5kporn.com/video/5KT9/photoset?page=2').mock(return_value=httpx.Response(200, text=''))
    detail = await Network5KPClient().fetch_scene_detail(scene_url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == '5Kporn'
    assert detail.tagline == '5Kteens'
    assert detail.collections == ['5Kteens']
    assert detail.release_date == '2021-03-04'
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://cdn/jane.jpg'
    assert detail.scene_url == scene_url
    assert detail.art == ['https://cdn/g1.jpg', 'https://cdn/p1.jpg']
