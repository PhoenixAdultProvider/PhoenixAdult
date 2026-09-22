from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.sites.stasyq import StasyQClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site

SITE = find_site('StasyQ')
assert SITE is not None

SCENE_HTML = """<html><body>
  <h1>Crystal Blue</h1>
  <div class="about-section__text"><p>A glossy shoot.</p></div>
  <section class="about-section"><div class="tags"><a>Solo</a><a>Glamour</a></div></section>
  <section class="content-section"><div class="release-card__model"><a>Stasy Q</a></div></section>
  <div class="js-release-gallery "><a href="https://cdn.sq.com/1.jpg">x</a><a href="https://cdn.sq.com/2.jpg">y</a></div>
</body></html>"""


@respx.mock
async def test_search_by_scene_id() -> None:
    respx.get('https://www.stasyq.com/r/Q/1234').mock(return_value=httpx.Response(200, text=SCENE_HTML))
    results: list[SearchResult] = []
    await StasyQClient().search(
        results, SearchContext(title='Crystal 1234', encoded='Crystal 1234', search_site=SITE.name, site_info=SITE, full_title='Crystal 1234')
    )
    assert len(results) == 1
    assert results[0].title == 'Crystal Blue'
    assert results[0].scene_url == 'https://www.stasyq.com/r/Q/1234'
    assert results[0].score == 100


@respx.mock
async def test_search_no_numeric_token() -> None:
    results: list[SearchResult] = []
    await StasyQClient().search(results, SearchContext(title='no digits here', encoded='x', search_site=SITE.name, site_info=SITE))
    assert results == []


@respx.mock
async def test_detail() -> None:
    url = 'https://www.stasyq.com/r/Q/1234'
    respx.get(url).mock(return_value=httpx.Response(200, text=SCENE_HTML))
    detail = await StasyQClient().fetch_scene_detail(f'{url}|2024-03-02', SITE)
    assert detail is not None
    assert detail.title == 'Crystal Blue'
    assert detail.summary == 'A glossy shoot.'
    assert detail.studio == 'StasyQ'
    assert detail.tagline == ''
    assert detail.collections == ['StasyQ']
    assert detail.release_date == '2024-03-02'
    assert detail.genres == ['Solo', 'Glamour']
    assert [a.name for a in detail.actors] == ['Stasy Q']
    assert detail.art == ['https://cdn.sq.com/1.jpg', 'https://cdn.sq.com/2.jpg']
