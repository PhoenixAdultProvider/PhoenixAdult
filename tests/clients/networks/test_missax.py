from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext
from app.clients.networks.missax import MissaXClient
from app.registry import find_site

SITE = find_site('MissaX')
FYRE = find_site('House of Fyre')
assert SITE is not None and FYRE is not None


def _ctx(site, title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=site.name, site_info=site, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search() -> None:
    url = 'https://missax.com/tour/search.php?query=cool+scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text='<div class="updateItem"><a href="/scene/77"></a><h4><a>Cool Scene</a></h4><span class="update_thumb_date">March 4, 2021</span></div>',
        )
    )
    results = await MissaXClient().search(_ctx(SITE))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://missax.com/scene/77'
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_detail() -> None:
    url = 'https://missax.com/scene/77'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <span class="update_title">Cool Scene</span>
              <span class="latest_update_description">Synopsis: A summary.</span>
              <span class="update_date">March 4, 2021 Available to Members Now</span>
              <div class="update_block"><span class="tour_update_models"><a href="/model/jane">Jane Doe</a></span></div>
              <span class="update_tags"><a>Taboo</a><a>Taboo</a></span>
              <img class="update_thumb" src0_4x="https://cdn/big.jpg?token=x" src0_1x="https://cdn/small.jpg?token=y" />
            </body></html>""",
        )
    )
    respx.get('https://missax.com/model/jane').mock(return_value=httpx.Response(200, text='<img class="model_bio_thumb" src0_1x="/p/jane.jpg" />'))
    detail = await MissaXClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'MissaX'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Taboo']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://missax.com/p/jane.jpg'
    assert detail.raw_image_urls == ['https://cdn/big.jpg?token=x', 'https://cdn/small.jpg?token=y']


@respx.mock
async def test_house_of_fyre_title_strip() -> None:
    url = 'https://www.houseofyre.com/scene/9'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <span class="update_title">Cool Scene: Jane Doe</span>
              <div class="update_block"><span class="tour_update_models"><a href="/model/jane">Jane Doe</a></span></div>
            </body></html>""",
        )
    )
    respx.get('https://www.houseofyre.com/model/jane').mock(return_value=httpx.Response(200, text='<div></div>'))
    detail = await MissaXClient().fetch_scene_detail(url, FYRE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
