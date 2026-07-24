from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.networks.pkjmedia import PKJMediaClient
from phoenixadult.registry import find_site

SITE = find_site('My POV Fam')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search() -> None:
    url = 'https://www.mypovfam.com/?s=cool+scene'
    html = (
        '<ul class="bricks-layout-wrapper"><div class="bricks-layout-inner"><div>'
        '<h3><a href="https://www.mypovfam.com/scene/7">Cool Scene</a></h3>'
        '</div></div></ul>'
    )
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await PKJMediaClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://www.mypovfam.com/scene/7'


@respx.mock
async def test_detail() -> None:
    url = 'https://www.mypovfam.com/scene/7'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1 class="brxe-post-title">Cool Scene</h1>
              <div class="brxe-post-content"><p><span>A summary.</span></p></div>
              <div class="brxe-post-meta"><span><a>Jane Doe</a></span></div>
              <video class="bricks-plyr" poster="/img/p.jpg"></video>
            </body></html>""",
        )
    )
    detail = await PKJMediaClient().fetch_scene_detail('https://www.mypovfam.com/scene/7|2021-03-04', SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'PKJ Media'
    assert detail.tagline == 'My POV Fam'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Family', 'Pov']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.art == ['https://www.mypovfam.com/img/p.jpg']
