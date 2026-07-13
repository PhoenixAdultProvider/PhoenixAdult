from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites.alsangels import AlsAngelsClient
from app.registry import find_site

SITE = find_site('ALS Angels')
assert SITE is not None

_ROW = (
    '<tr>'
    '<td class="videothumbnail"><a href="../graphics/g1.jpg"><img src="../graphics/videos/jane01.jpg" /></a></td>'
    '<h2 class="videomodel">Models: Jane Doe</h2>'
    '<span class="videotype">Video Type: Masturbation</span>'
    '<span class="videodate">Date: 03/04/2021</span>'
    '<span class="videodescription">A summary.</span>'
    '</tr>'
)


def _ctx(title: str = 'Jane Doe Masturbation', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search() -> None:
    respx.get('https://alsangels.com/dailyvideos.html').mock(return_value=httpx.Response(200, text=f'<table>{_ROW}</table>'))
    results: list[SearchResult] = []
    await AlsAngelsClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].score == 100
    assert results[0].scene_url == 'https://alsangels.com/profiles/jane01'
    assert AlsAngelsClient().decode(results[0].cur_id) == 'jane01|2021-03-04'


@respx.mock
async def test_detail() -> None:
    page = (
        '<html><head><title>ALSAngels.com - Jane Doe</title></head><body>'
        '<div id="modelbioheadshot"><img src="../p/jane.jpg" /></div>'
        f'<table>{_ROW}</table></body></html>'
    )
    respx.get('https://alsangels.com/profiles/jane.html').mock(return_value=httpx.Response(200, text=page))
    detail = await AlsAngelsClient().fetch_scene_detail('jane01|2021-03-04', SITE)
    assert detail is not None
    assert detail.title == 'Jane Doe #1: Masturbation'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'ALS Angels'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Masturbation']
    assert detail.actors is not None and detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://alsangels.com/p/jane.jpg'
    assert detail.actors[0].gender == 'female'
    assert detail.art == ['https://alsangels.com/graphics/videos/jane01.jpg', 'https://alsangels.com/graphics/g1.jpg']


@respx.mock
async def test_detail_scene_id_trailing_suffix() -> None:
    row = _ROW.replace('../graphics/videos/jane01.jpg', '../graphics/videos/stormrose006-nn.jpg').replace('Jane Doe', 'Storm Rose')
    page = f'<html><head><title>ALSAngels.com - Storm Rose</title></head><body><table>{row}</table></body></html>'
    respx.get('https://alsangels.com/profiles/stormrose.html').mock(return_value=httpx.Response(200, text=page))
    detail = await AlsAngelsClient().fetch_scene_detail('stormrose006-nn|2021-03-04', SITE)
    assert detail is not None
    assert detail.title == 'Storm Rose #6: Masturbation'
