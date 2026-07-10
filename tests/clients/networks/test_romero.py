from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext
from app.clients.networks.romero import RomeroClient, _clean_poster
from app.registry import find_site

SITE = find_site('Hentaied')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


def test_clean_poster() -> None:
    assert _clean_poster('https://h/cdn?src=https://real/img-scaled.jpg') == 'https://real/img.jpg'
    assert _clean_poster('https://real/img.jpg') == 'https://real/img.jpg'


@respx.mock
async def test_search() -> None:
    url = 'https://hentaied.com/?s=cool+scene'
    respx.get(url).mock(return_value=httpx.Response(200, text='<div class="half"><a href="/scene/7"></a><h2>Cool Scene</h2></div>'))
    results = await RomeroClient().search(_ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].scene_url == 'https://hentaied.com/scene/7'


@respx.mock
async def test_detail() -> None:
    url = 'https://hentaied.com/scene/7'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><head>
              <meta itemprop="name" content="Cool Scene | Hentaied" />
              <meta property="article:published_time" content="2021-03-04T10:00:00+00:00" />
              </head><body>
              <div class="cont"><p>A summary.</p></div>
              <div class="Cats"><a>Tentacles</a></div>
              <div class="tagsmodels"><img alt="model icon" /><a>Jane Doe</a></div>
              <div class="director"><a>Mr Romero</a></div>
              <img class="alignnone size-full" src="https://cdn/img-scaled.jpg" />
            </body></html>""",
        )
    )
    detail = await RomeroClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Romero Multimedia'
    assert detail.tagline == 'Hentaied'
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Tentacles']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.directors is not None and detail.directors[0].name == 'Mr Romero'
    assert detail.raw_image_urls == ['https://cdn/img.jpg']


@respx.mock
async def test_detail_loose_actors() -> None:
    site = find_site('Defeated Sex Fight')
    assert site is not None
    url = 'https://defeatedsexfight.com/scene/9'
    respx.get(url).mock(
        return_value=httpx.Response(200, text='<html><body><h1>X</h1><div class="tagsmodels"><a>Fighter A</a><a>Fighter B</a></div></body></html>')
    )
    detail = await RomeroClient().fetch_scene_detail(url, site)
    assert detail is not None
    assert [a.name for a in detail.actors] == ['Fighter A', 'Fighter B']
