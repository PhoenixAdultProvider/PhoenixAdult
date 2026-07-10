from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext
from app.clients.networks.purecfnm import PureCFNMClient
from app.registry import find_site

SITE = find_site('Girls Abuse Guys')
assert SITE is not None


def _ctx(title: str = 'Jane Doe Cool Scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search_and_detail_roundtrip() -> None:
    url = 'https://girlsabuseguys.com/models/Jane-Doe.html'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<div class="update_block">
              <span class="update_title">Cool Scene</span>
              <span class="latest_update_description">A summary.</span>
              <span class="update_date">March 4, 2021</span>
              <span class="tour_update_models"><a>Jane Doe</a><a>Mistress X</a></span>
              <div class="update_image"><a><img src="https://cdn/p.jpg" /></a></div>
            </div>""",
        )
    )
    results = await PureCFNMClient().search(_ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].display_date == '2021-03-04'

    detail = await PureCFNMClient().fetch_scene_detail(PureCFNMClient().decode(results[0].cur_id), SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'PureCFNM'
    assert detail.tagline == 'Girls Abuse Guys'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['CFNM', 'Femdom', 'Male Humiliation', 'Threesome']
    assert [a.name for a in detail.actors] == ['Jane Doe', 'Mistress X']
    assert detail.raw_image_urls == ['https://cdn/p.jpg']
