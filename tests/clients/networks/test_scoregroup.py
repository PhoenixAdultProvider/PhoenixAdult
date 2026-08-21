from __future__ import annotations

from urllib.parse import parse_qs

import httpx
import pytest
import respx

import phoenixadult.clients.networks.scoregroup as sg_mod
from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.networks.scoregroup import ScoreGroupClient
from phoenixadult.registry import find_site


async def _no_web_search(*_a: object, **_k: object) -> list[str]:
    return []


SITE = find_site('Scoreland')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _no_web(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sg_mod, 'web_search_urls', _no_web_search)


@respx.mock
async def test_search_posts_the_query_as_form_data() -> None:
    html = (
        '<div class="compact video">'
        '<a class="title" href="https://scoreland.com/big-boob-videos/jane/777/">Cool Scene</a>'
        '<small class="i-model">Jane Doe</small><img src="https://cdn/t.jpg" /></div>'
    )
    route = respx.post('https://scoreland.com/search-es').mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await ScoreGroupClient().search(results, _ctx(scene_id='777'))

    request = route.calls.last.request
    assert request.headers['content-type'] == 'application/x-www-form-urlencoded'
    assert parse_qs(request.content.decode()) == {'keywords': ['cool scene'], 's_filters[type]': ['videos'], 's_filters[site]': ['current']}
    assert not request.url.query

    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].score == 100


@respx.mock
async def test_detail() -> None:
    import json

    packed = json.dumps({'url': 'https://scoreland.com/big-boob-videos/jane/777/', 'date': '2021-03-04', 'title': 'Cool Scene'})
    respx.get('https://scoreland.com/big-boob-videos/jane/777/').mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1>Cool Scene</h1>
              <div class="p-desc">A summary.</div>
              <div><span class="value">x</span><span class="value">March 4, 2021</span></div>
              <div class="mb-3"><a>Big Tits</a></div>
              <div><span class="value"><a href="/model/jane">Jane Doe</a></span></div>
              <div class="thumb"><img src="https://cdn/p.jpg" /></div>
            </body></html>""",
        )
    )
    respx.get('https://scoreland.com/model/jane').mock(return_value=httpx.Response(200, text='<div class="item-img"><img src="https://cdn/jane.jpg" /></div>'))
    detail = await ScoreGroupClient().fetch_scene_detail(packed, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Score Group'
    assert detail.tagline == 'Scoreland'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Big Tits']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://cdn/jane.jpg'
    assert detail.art == ['https://cdn/p.jpg']
