from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.networks.thickcash import ThickCashClient
from app.registry import find_site

SITE = find_site('Ebony Tugs')
assert SITE is not None


def _ctx(title: str = 'Jane Doe Cool Scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search_and_detail_roundtrip() -> None:
    url = 'https://ebonytugs.com/models/Jane-Doe.html'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text='<div class="updateBlock clear"><h3>Cool Scene</h3><p>A summary.</p><h4>Added: March 4, 2021</h4><img src="https://cdn/p.jpg" /></div>',
        )
    )
    results: list[SearchResult] = []
    await ThickCashClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].display_date == '2021-03-04'

    detail = await ThickCashClient().fetch_scene_detail(ThickCashClient().decode(results[0].cur_id), SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Thick Cash'
    assert detail.tagline == 'Ebony Tugs'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Ebony', 'Handjob']
    assert detail.actors == []
    assert detail.art == ['https://cdn/p.jpg']
