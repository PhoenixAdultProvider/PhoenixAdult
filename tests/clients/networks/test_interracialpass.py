from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.networks.interracialpass import InterracialPassClient
from phoenixadult.registry import find_site

SITE = find_site('Interracial Pass')
BBC = find_site('BBC Surprise')
assert SITE is not None and BBC is not None


def _ctx(site: object, title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '%20'), search_site=site.name, site_info=site, **kw)  # type: ignore[union-attr,arg-type]


@respx.mock
async def test_search_direct_and_onsite() -> None:
    direct = 'https://www.interracialpass.com/t1/trailers/cool-scene.html'
    respx.get(direct).mock(
        return_value=httpx.Response(
            200, text='<div class="video-player"><h2 class="section-title">Cool Scene</h2></div><div class="update-info-row">Released: March 4, 2021</div>'
        )
    )
    respx.get('https://www.interracialpass.com/t1/search.php?query=cool+scene').mock(return_value=httpx.Response(200, text='<html></html>'))
    results: list[SearchResult] = []
    await InterracialPassClient().search(results, _ctx(SITE))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == direct
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_detail_bbc_twins() -> None:
    url = 'https://bbcsurprise.com/t1/trailers/x.html'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <div class="video-player"><h3 class="section-title">Cool Scene</h3></div>
              <div class="update-info-block">x</div>
              <div class="update-info-block">Description: A summary.</div>
              <div class="update-info-row">Released: March 4, 2021</div>
              <ul class="tags"><li><a>Anal</a></li></ul>
              <div class="models-list-thumbs"><li><span>Twins</span><img src0_3x="/p/twins.jpg" /></li></div>
              <div class="player-thumb"><img src0_1x="/img/t.jpg" /></div>
            </body></html>""",
        )
    )
    detail = await InterracialPassClient().fetch_scene_detail(url, BBC)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'ExploitedX'
    assert detail.tagline == 'BBC Surprise'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Anal']
    assert [a.name for a in detail.actors] == ['Joey White', 'Sami White']
    assert detail.actors[0].photo_url == 'https://bbcsurprise.com/p/twins.jpg'
    assert detail.art == ['https://bbcsurprise.com/img/t.jpg']
