from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.networks.porndoepremium import PorndoePremiumClient
from app.registry import find_site

SITE = find_site('Chicas Loca')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search() -> None:
    url = 'https://mamacitaz.com/search.en.html?q=cool+scene'
    html = (
        '<div class="main-content"><div class="-g-vc-grid">'
        '<div class="-g-vc-item-title"><a href="/v/7" title="Cool Scene"></a></div>'
        '<div class="-g-vc-item-date">2021-03-04</div></div></div>'
    )
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await PorndoePremiumClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://mamacitaz.com/v/7'
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_detail() -> None:
    url = 'https://mamacitaz.com/v/7'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1 class="-mvd-heading">Cool Scene</h1>
              <div class="-mvd-description">A summary.</div>
              <div class="-mvd-grid-actors"><span><a href="/model/jane" title="Jane Doe">Jane Doe</a></span></div>
              <span class="-mvd-list-item"><a>Latina</a></span>
              <div class="-mvd-grid-stats">HD • 30 min • 2021-03-04</div>
              <picture class="-vcc-picture"><img src="https://cdn/p.jpg" /></picture>
            </body></html>""",
        )
    )
    respx.get('https://mamacitaz.com/model/jane').mock(
        return_value=httpx.Response(
            200, text='<div class="-aph-heading"><h1>Jane Doe</h1></div><div class="-api-poster-item"><img src="https://cdn/jane.jpg" /></div>'
        )
    )
    detail = await PorndoePremiumClient().fetch_scene_detail('https://mamacitaz.com/v/7', SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Porndoe Premium'
    assert detail.tagline == 'Jane Doe'
    assert detail.collections == ['Jane Doe']
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Latina']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://cdn/jane.jpg'
    assert detail.raw_image_urls == ['https://cdn/p.jpg']
