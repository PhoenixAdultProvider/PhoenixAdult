from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.networks.fuelvirtual import FuelVirtualClient
from phoenixadult.registry import find_site

SITE = find_site('FuckedHard18')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search() -> None:
    url = 'https://fuckedhard18.com/membersarea/search.php?st=advanced&site[]=5&qall=cool+scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<div align="left">
              <td valign="top">thumb</td>
              <td valign="top"><a href="vids.php?id=434">Cool Scene</a></td>
              <span class="date">Added March 4, 2021</span>
            </div>""",
        )
    )
    results: list[SearchResult] = []
    await FuelVirtualClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://fuckedhard18.com/membersarea/vids.php?id=434'
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_detail_uses_actor_db() -> None:
    url = 'https://fuckedhard18.com/membersarea/vids.php?id=434'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><head><title>Cool Scene - FuckedHard18</title></head><body>
              <td class="plaintext"><a class="model_category_link">Teen</a></td>
              <div id="description"><td align="left"><a>Wrong Name</a></td></div>
              <a class="jqModal"><img src="/img/t.jpg" /></a>
            </body></html>""",
        )
    )
    respx.get('https://fuckedhard18.com/membersarea/highres.php?id=434').mock(return_value=httpx.Response(200, text='<html></html>'))
    detail = await FuelVirtualClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.studio == 'FuelVirtual'
    assert detail.tagline == 'FuckedHard18'
    assert detail.genres == ['Teen', '18-Year-Old']
    assert [a.name for a in detail.actors] == ['Abby Lane']
    assert detail.art == ['https://fuckedhard18.com/img/t.jpg']
