from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites.vrallure import VRAllureClient
from app.registry import find_site

SITE = find_site('VRAllure')
assert SITE is not None


@respx.mock
async def test_search_canonical_adoption() -> None:
    request_url = 'https://www.vrallure.com/scenes/wild_scene'
    canonical = 'https://www.vrallure.com/scenes/123/wild-scene'
    respx.get(request_url).mock(
        return_value=httpx.Response(
            200,
            text=f"""<html><head><link rel="canonical" href="{canonical}" /></head><body>
              <h1 class="latest-scene-title">Wild Scene</h1>
              <p class="publish-date">January 5, 2024</p>
            </body></html>""",
        )
    )
    results: list[SearchResult] = []
    await VRAllureClient().search(results, SearchContext(title='wild scene', encoded='x', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].scene_url == canonical
    assert results[0].title == 'Wild Scene'
    assert results[0].release_date == '2024-01-05'


@respx.mock
async def test_search_empty_on_404() -> None:
    respx.get('https://www.vrallure.com/scenes/no_such').mock(return_value=httpx.Response(404, text=''))
    results: list[SearchResult] = []
    await VRAllureClient().search(results, SearchContext(title='no such', encoded='x', search_site=SITE.name, site_info=SITE))
    assert results == []


@respx.mock
async def test_detail() -> None:
    url = 'https://www.vrallure.com/scenes/123/wild-scene'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><head><meta property="og:image" content="//cdn.vra.com/og.jpg" /></head><body>
              <h1 class="latest-scene-title">Wild Scene</h1>
              <p class="desc"><span>Lots of fun.</span></p>
              <p class="publish-date">January 5, 2024</p>
              <a class="label label-tag">Anal</a>
              <a class="label label-tag">Hardcore</a>
              <p class="model-name"><a href="https://www.vrallure.com/models/jane">Jane Doe</a></p>
            </body></html>""",
        )
    )
    respx.get('https://www.vrallure.com/models/jane').mock(
        return_value=httpx.Response(200, text='<html><body><img id="model-thumbnail" src="//cdn.vra.com/jane.jpg" /></body></html>')
    )
    detail = await VRAllureClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Wild Scene'
    assert detail.summary == 'Lots of fun.'
    assert detail.studio == 'VRAllure'
    assert detail.tagline == 'VRAllure'
    assert detail.collections == ['VRAllure']
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['Anal', 'Hardcore']
    assert [(a.name, a.photo_url) for a in detail.actors] == [('Jane Doe', 'https://cdn.vra.com/jane.jpg')]
    assert detail.art == ['https://cdn.vra.com/og.jpg', 'https://cdn.vra.com/jane.jpg']
