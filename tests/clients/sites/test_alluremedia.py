from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.sites.alluremedia import AllureMediaClient
from phoenixadult.registry import find_site

SITE = find_site('Amateur Allure')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search() -> None:
    html = (
        '<div class="update_details">'
        '<div class="update_title"><a href="/v/7">Cool Scene</a></div>'
        '<a href="/v/7"></a>'
        '<div class="update_date">Added: 03/04/2021</div></div>'
    )
    respx.get(url__startswith='https://amateurallure.com/tour/search.php').mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await AllureMediaClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://amateurallure.com/v/7'
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_detail() -> None:
    url = 'https://amateurallure.com/v/7'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><head><title>Cool Scene</title></head><body>
              <span class="update_description">A summary with Jane Wilde.</span>
              <div class="update_date">March 4, 2021</div>
              <span class="update_tags"><a>B--w--b</a><a>Teen</a></span>
              <div class="backgroundcolor_info"><span class="update_models"><a href="/model/jane">Jane Doe</a></span></div>
            </body></html>""",
        )
    )
    respx.get('https://amateurallure.com/model/jane').mock(
        return_value=httpx.Response(200, text='<div class="cell_top cell_thumb"><img src="/p/jane-1x.jpg" /></div>')
    )
    detail = await AllureMediaClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary with Jane Wilde.'
    assert detail.studio == 'Allure Media'
    assert detail.tagline == 'Amateur Allure'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['blowjob', 'teen', 'Amateur']
    names = [a.name for a in (detail.actors or [])]
    assert 'Jane Doe' in names
    assert 'Jane Wilde' in names
    assert (detail.actors or [])[0].photo_url == 'https://amateurallure.com/p/jane-3x.jpg'
