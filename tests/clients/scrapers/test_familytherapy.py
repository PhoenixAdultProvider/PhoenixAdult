from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext
from app.clients.sites.familytherapy import FamilyTherapyClient
from app.registry import find_site

SITE = find_site('Family Therapy')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search_direct() -> None:
    html = '<article><h2><a href="/v/7">Cool Scene</a></h2><p><span>March 4, 2021</span></p></article>'
    respx.get(url__startswith='https://familytherapyxxx.com/?s=').mock(return_value=httpx.Response(200, text=html))
    results = await FamilyTherapyClient().search(_ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://familytherapyxxx.com/v/7'
    assert FamilyTherapyClient().decode(results[0].cur_id).endswith('|0')


@respx.mock
async def test_detail_direct() -> None:
    url = 'https://familytherapyxxx.com/v/7'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1>cool scene title</h1>
              <p class="post-meta"><span>Mar 4, 2021</span></p>
              <div class="entry-content">
                <p>A summary. Starring Jane Doe & John Smith.</p>
              </div>
              <a rel="category tag">Taboo</a>
            </body></html>""",
        )
    )
    detail = await FamilyTherapyClient().fetch_scene_detail(f'{url}|2021-03-04|0', SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene Title'
    assert detail.studio == 'Family Therapy'
    assert detail.tagline == 'Family Therapy'
    assert detail.collections == ['Family Therapy']
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Taboo']
    names = [a.name for a in (detail.actors or [])]
    assert names == ['Jane Doe', 'John Smith']
