from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext
from app.clients.networks.pornworld import PornWorldClient
from app.registry import find_site

SITE = find_site('DDF Busty')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search_direct_id() -> None:
    url = 'https://ddfbusty.com/watch/12345'
    respx.get(url).mock(return_value=httpx.Response(200, text='<title>Cool Scene - PornWorld</title>'))
    results = await PornWorldClient().search(_ctx(scene_id='12345'))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].score == 100


@respx.mock
async def test_search_onsite() -> None:
    url = 'https://ddfbusty.com/videos/freeword/cool+scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text='<h1 class="section__title">Results</h1><div class="card-scene"><div class="card-scene__text"><a href="/watch/7">Cool Scene</a></div></div>',
        )
    )
    results = await PornWorldClient().search(_ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://ddfbusty.com/watch/7'


@respx.mock
async def test_detail() -> None:
    url = 'https://ddfbusty.com/watch/7'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><head><title>Cool Scene - PornWorld</title></head><body>
              <div>Description:</div><div>A summary.</div>
              <i class="bi-calendar"> 2021-03-04 </i>
              <div class="genres-list"><a>Busty</a><a>Busty</a></div>
              <h1 class="watch__title"><a>Jane Doe</a></h1>
              <video data-poster="https://cdn/p.jpg"></video>
            </body></html>""",
        )
    )
    detail = await PornWorldClient().fetch_scene_detail('https://ddfbusty.com/watch/7', SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'PornWorld'
    assert detail.tagline == 'DDF Busty'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Busty']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.raw_image_urls == ['https://cdn/p.jpg']
