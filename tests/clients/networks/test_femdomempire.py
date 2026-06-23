from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext
from app.clients.networks.femdomempire import FemdomEmpireClient
from app.registry import find_site

SITE = find_site('Femdom Empire')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search_advanced() -> None:
    url = 'https://femdomempire.com/tour/search.php?st=advanced&qany=cool+scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text='<div class="item-info"><a href="/tour/trailers/cool.html">Cool Scene</a><span class="date">March 4, 2021</span></div>',
        )
    )
    results = await FemdomEmpireClient().search(_ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://femdomempire.com/tour/trailers/cool.html'
    assert results[0].score is not None


@respx.mock
async def test_search_manual_match() -> None:
    url = 'https://femdomempire.com/tour/search.php?st=advanced&qany=Cock+Locked'
    respx.get(url).mock(return_value=httpx.Response(200, text='<html></html>'))
    results = await FemdomEmpireClient().search(_ctx(title='Cock Locked'))
    assert len(results) == 1
    assert results[0].title == 'Cock Locked'
    assert results[0].scene_url == 'https://femdomempire.com/tour/trailers/CockLocked.html'
    assert results[0].score == 101


@respx.mock
async def test_detail() -> None:
    url = 'https://femdomempire.com/tour/trailers/cool.html'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <div class="videoDetails"><h3>Cool Scene</h3><p>A summary.</p></div>
              <div class="videoInfo clear"><p>Date Added: March 4, 2021</p></div>
              <div class="featuring"><ul><li>Featuring: Jane Doe</li></ul></div>
              <div class="featuring"><ul><li>Categories: Strapon</li><li>Tags: Pegging</li></ul></div>
              <a class="fake_trailer"><img src0_1x="/img/t.jpg" /></a>
            </body></html>""",
        )
    )
    detail = await FemdomEmpireClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Femdom Empire'
    assert detail.tagline == 'Femdom Empire'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['strapon', 'pegging', 'Femdom']  # 2nd featuring + constant
    assert [a.name for a in detail.actors] == ['Jane Doe']
    assert detail.raw_image_urls == ['https://femdomempire.com/img/t.jpg']
