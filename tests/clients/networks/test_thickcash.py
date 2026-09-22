from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.networks.thickcash import ThickCashClient
from phoenixadult.models.scrape import SearchResult
from phoenixadult.registry import find_site
from tests.support import search_context

SITE = find_site('Ebony Tugs')
assert SITE is not None


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
    await ThickCashClient().search(results, search_context(SITE, 'Jane Doe Cool Scene'))
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
