from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.networks.fakings import FAKingsClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site

SITE = find_site('FAKings')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '%20'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search_both_surfaces() -> None:
    row = """<div class="zona-listado2">
      <a href="/en/video/77/cool-scene"><h3>Cool Scene</h3></a>
      <p class="txtmininfo calen sinlimite">2021-03-04</p>
    </div>"""
    respx.get('https://www.fakings.com/en/buscar/cool-scene').mock(return_value=httpx.Response(200, text=row))
    respx.get('https://www.fakings.com/buscar/cool-scene').mock(return_value=httpx.Response(200, text='<html></html>'))
    results: list[SearchResult] = []
    await FAKingsClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://www.fakings.com/en/video/77/cool-scene'
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_detail() -> None:
    url = 'https://www.fakings.com/en/video/77/cool-scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <h1>Cool Scene</h1>
              <span class="grisoscuro">A summary.</span>
              <p><strong>Serie:</strong> <a href="/s/milf">milf club</a></p>
              <p><strong>Categorias:</strong> <a>Anal</a><a>MILF</a></p>
              <p><strong>Actrices:</strong> <a href="/en/model/jane">Jane Doe</a></p>
            </body></html>""",
        )
    )
    model = """<html><body>
      <div class="zona-imagen"><img class="x" src="/p/jane.jpg" /></div>
      <div class="zona-listado2"><a href="/en/video/77/cool-scene"></a><img class="t" src="/img/poster.jpg" /></div>
    </body></html>"""
    respx.get('https://www.fakings.com/en/model/jane').mock(return_value=httpx.Response(200, text=model))
    detail = await FAKingsClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'FAKings'
    assert detail.tagline == 'MILF Club'
    assert detail.collections == ['MILF Club']
    assert detail.genres == ['Anal', 'MILF']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://www.fakings.com/p/jane.jpg'
    assert detail.art == ['https://www.fakings.com/img/poster.jpg']
