from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.networks.gammaent import GammaEntClient
from app.registry import find_site

SITE = find_site('Sunny Leone')
TERA = find_site('Tera Patrick')
assert SITE is not None and TERA is not None


def _ctx(site: object, title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '%20'), search_site=site.name, site_info=site, **kw)  # type: ignore[union-attr,arg-type]


async def test_search_disabled_site() -> None:
    results: list[SearchResult] = []
    await GammaEntClient().search(results, _ctx(TERA))
    assert results == []


@respx.mock
async def test_search() -> None:
    row = """<div class="tlcDetails"><a href="/en/movie/cool/123">Cool Scene</a>
      <div class="tlcSpecs"><span class="tlcSpecsDate"><span class="tlcDetailsValue">March 4, 2021</span></span></div>
    </div>"""
    respx.get('http://www.sunnyleone.com/en/search/scene/cool%20scene').mock(return_value=httpx.Response(200, text=row))
    respx.get('http://www.sunnyleone.com/en/search/scene/cool%20scene/2').mock(return_value=httpx.Response(200, text='<html></html>'))
    results: list[SearchResult] = []
    await GammaEntClient().search(results, _ctx(SITE))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'http://www.sunnyleone.com/en/movie/cool/123'
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_detail() -> None:
    url = 'http://www.sunnyleone.com/en/video/cool/123'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><head>
              <meta name="twitter:title" content="Cool Scene" />
              <meta name="twitter:description" content="A summary." />
              <meta name="twitter:image" content="https://cdn/og.jpg" />
              </head><body>
              <div class="studioLink">Cool Studio</div>
              <span class="updatedDate">| March 4, 2021 |</span>
              <div class="sceneCol sceneColCategories"><a>Anal</a><a>Gonzo</a></div>
              <div class="sceneCol sceneColActors"><a href="/en/pornstar/jane/1">Jane Doe</a></div>
              <div class="sceneCol sceneColDirectors"><a>Some Director</a></div>
            </body></html>""",
        )
    )
    respx.get('http://www.sunnyleone.com/en/pornstar/jane/1').mock(return_value=httpx.Response(200, text='<img class="actorPicture" src="/p/jane.jpg" />'))
    detail = await GammaEntClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Open Life Network'
    assert detail.tagline == 'Cool Studio'
    assert detail.collections == ['Cool Studio']
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['anal', 'gonzo']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'http://www.sunnyleone.com/p/jane.jpg'
    assert detail.directors is not None and detail.directors[0].name == 'Some Director'
    assert 'https://cdn/og.jpg' in detail.art
