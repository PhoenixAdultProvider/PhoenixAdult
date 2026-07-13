from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.networks.queensnake import QueenSnakeClient
from app.registry import find_site

SITE = find_site('QueenSnake')
assert SITE is not None


def _ctx(title: str = 'Cool Scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search() -> None:
    url = 'https://queensnake.com/previewmovie/cool-scene/'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text='<div class="contentBlock"><span class="contentFilmName">Cool Scene</span><span class="contentFileDate">2021 March 4 • HD</span></div>',
        )
    )
    results: list[SearchResult] = []
    await QueenSnakeClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_search_no_match_pager() -> None:
    url = 'https://queensnake.com/previewmovie/nope/'
    respx.get(url).mock(
        return_value=httpx.Response(
            200, text='<div class="pagerWrapper"><a href="/previewmovies/0"></a></div><div class="contentBlock"><span class="contentFilmName">X</span></div>'
        )
    )
    results: list[SearchResult] = []
    await QueenSnakeClient().search(results, _ctx('nope'))
    assert results == []


@respx.mock
async def test_detail() -> None:
    url = 'https://queensnake.com/previewmovie/cool-scene/'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <span class="contentFilmName">Cool Scene</span>
              <div class="contentPreviewDescription">A summary.</div>
              <span class="contentFileDate">2021 March 4 • HD</span>
              <div class="contentPreviewTags"><a>Needles</a><a>Abby</a></div>
              <div class="contentBlock"><img src="https://cdn/preview1.jpg?x=1" /></div>
            </body></html>""",
        )
    )
    detail = await QueenSnakeClient().fetch_scene_detail('https://queensnake.com/previewmovie/cool-scene/', SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'QueenSnake'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['BDSM', 'S&M', 'Needles', 'Abby']
    assert [a.name for a in detail.actors] == ['Abby']
    assert detail.raw_image_urls == ['https://cdn/preview1.jpg?x=1']
