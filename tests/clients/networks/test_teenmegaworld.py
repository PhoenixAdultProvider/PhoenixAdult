from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.networks.teenmegaworld import TeenMegaWorldClient
from app.registry import find_site

SITE = find_site('Old-n-Young')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search() -> None:
    card = '<div class="thumb thumb-video"><a class="thumb__title-link" href="/v/7">Cool Scene</a><time>March 4, 2021</time></div>'
    respx.get('https://old-n-young.com/search.php?query=cool+scene&page=1').mock(return_value=httpx.Response(200, text=card))
    respx.get('https://old-n-young.com/search.php?query=cool+scene&page=2').mock(return_value=httpx.Response(200, text=''))
    results: list[SearchResult] = []
    await TeenMegaWorldClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://old-n-young.com/v/7'
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_detail() -> None:
    url = 'https://old-n-young.com/v/7'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1 id="video-title">Cool Scene</h1>
              <p class="video-description-text">A summary.</p>
              <a class="video-site-link btn">Old N Young</a>
              <span title="Video release date">March 4, 2021</span>
              <a class="video-tag-link">Teen</a>
              <a class="video-actor-link actor__link" href="/model/jane">Jane Doe</a>
              <img id="video-cover-image" src="/img/c.jpg" />
            </body></html>""",
        )
    )
    respx.get('https://old-n-young.com/model/jane').mock(
        return_value=httpx.Response(200, text='<div class="model-profile-image-wrap"><img src="/p/jane.jpg" /></div>')
    )
    detail = await TeenMegaWorldClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Teen Mega World'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Teen']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://old-n-young.com/p/jane.jpg'
    assert detail.raw_image_urls == ['https://old-n-young.com/img/c.jpg']
