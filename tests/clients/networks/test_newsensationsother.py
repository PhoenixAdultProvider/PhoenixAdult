from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.networks.newsensationsother import NewSensationsOtherClient
from app.registry import find_site

SITE = find_site('The Tabu Tales')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search() -> None:
    url = 'https://thetabutales.com/tour_tt/search.php?query=cool+scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text='<div class="update_details"><a href="/scene/7.html">Cool Scene</a><div class="date_small">Date: 03/04/2021</div></div>',
        )
    )
    results: list[SearchResult] = []
    await NewSensationsOtherClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://thetabutales.com/scene/7.html'
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_detail_with_filmography_images() -> None:
    url = 'https://thetabutales.com/scene/7.html'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <div class="update_title">Cool Scene</div>
              <span class="update_description">A summary.</span>
              <span class="update_tags"><a>taboo</a><a>taboo</a></span>
              <span class="update_models"><a href="/models/jane.html">Jane Doe</a></span>
              <div class="mejs-layers"><img src="/img/poster.jpg" /></div>
            </body></html>""",
        )
    )
    actor_page = """<html><body>
      <div class="cell_top cell_thumb"><img src0_1x="/p/jane.jpg" /></div>
      <div class="table dvd_info"><div class="update_title">Cool Scene</div><div class="cell"><img src0_3x="/img/film1.jpg" /></div></div>
      <div class="table dvd_info"><div class="update_title">Other</div><div class="cell"><img src0_3x="/img/nope.jpg" /></div></div>
    </body></html>"""
    respx.get('https://thetabutales.com/models/jane.html').mock(return_value=httpx.Response(200, text=actor_page))
    detail = await NewSensationsOtherClient().fetch_scene_detail('https://thetabutales.com/scene/7.html|2021-03-04', SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'New Sensations'
    assert detail.tagline == 'The Tabu Tales'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Taboo']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://thetabutales.com/p/jane.jpg'
    assert detail.raw_image_urls == ['https://thetabutales.com/img/poster.jpg', 'https://thetabutales.com/img/film1.jpg']
