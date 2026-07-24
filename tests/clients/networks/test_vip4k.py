from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.networks.vip4k import VIP4KClient
from phoenixadult.registry import find_site

SITE = find_site('Sis')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search() -> None:
    html = '<div class="item__description"><a class="item__title" href="/en/videos/12345">Cool Scene</a><div class="item__date">March 4, 2021</div></div>'
    respx.get('https://vip4k.com/en/search/cool+scene').mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await VIP4KClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://vip4k.com/en/videos/12345'
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_direct_scene() -> None:
    respx.get('https://vip4k.com/en/videos/99999').mock(return_value=httpx.Response(200, text='<title>Sis | Cool Scene</title>'))
    results: list[SearchResult] = []
    await VIP4KClient().search(results, _ctx(scene_id='99999'))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'


@respx.mock
async def test_detail() -> None:
    url = 'https://vip4k.com/en/videos/12345'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><head><title>Sis | Cool Scene</title></head><body>
              <div class="player-description__text">A summary.</div>
              <a class="player-additional__site ph_register">Sis</a>
              <span class="player-additional__text">March 4, 2021</span>
              <div class="tags"><a>#Teen</a></div>
              <a class="player-description__model model ph_register"><div class="model__name">Jane Doe</div></a>
              <div class="player-item__block"><img data-src="//cdn/p.jpg" /></div>
            </body></html>""",
        )
    )
    detail = await VIP4KClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'VIP4K'
    assert detail.tagline == 'Sis.Porn'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Step Sister', 'Teen']
    assert detail.actors is not None and detail.actors[0].name == 'Jane Doe'
    assert detail.art == ['https://cdn/p.jpg']
