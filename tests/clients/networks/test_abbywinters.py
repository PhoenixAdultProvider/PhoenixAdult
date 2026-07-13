from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.networks.abbywinters import AbbyWintersClient, __testing__
from app.registry import find_site

SITE = find_site('Abby Winters')
assert SITE is not None
BASE = 'https://www.abbywinters.com'
SEARCH_URL = BASE + '/amateurs/models?filters%5Bkeyword%5D=foo'


@respx.mock
async def test_search_walks_model_to_scene() -> None:
    respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            text='<html><body><div id="browse-grid"><main><article><a class="m" href="https://www.abbywinters.com/models/alice"></a></article></main></div></body></html>',
        )
    )
    respx.get('https://www.abbywinters.com/models/alice').mock(
        return_value=httpx.Response(
            200,
            text="""<html><body><div id="subject-shoots">
              <h2><a href="https://www.abbywinters.com/scenes/scene-1">scene 1</a></h2>
              <h2><a href="https://www.abbywinters.com/shoots/blocked">no</a></h2>
            </div></body></html>""",
        )
    )
    respx.get('https://www.abbywinters.com/scenes/scene-1').mock(
        return_value=httpx.Response(
            200,
            text='<html><head><title>abbywinters.com : SubSite : Scene Title One | extra</title></head>'
            '<body><div id="shoot-featured-image"><h4>SubSite</h4></div>'
            '<table><tr><td>Scene</td><td><a href="https://www.abbywinters.com/models/alice-card">Alice</a></td></tr></table>'
            '</body></html>',
        )
    )
    respx.get('https://www.abbywinters.com/models/alice-card').mock(
        return_value=httpx.Response(
            200,
            text="""<html><body>
              <article class="card card-shoot">
                <span>March 4, 2021</span>
                <h2><a href="#">Scene Title One</a></h2>
                <h3>SubSite <span>HD</span></h3>
              </article>
            </body></html>""",
        )
    )
    results: list[SearchResult] = []
    await AbbyWintersClient().search(results, SearchContext(title='foo', encoded='foo', search_site=SITE.name, site_info=SITE))
    assert [r.title for r in results] == ['Scene Title One']
    assert results[0].scene_url == 'https://www.abbywinters.com/scenes/scene-1'
    assert results[0].display_date == '2021-03-04'


@respx.mock
async def test_search_zero_total_short_circuits() -> None:
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, text='<html><body><span id="browse-total-count">0</span></body></html>'))
    results: list[SearchResult] = []
    await AbbyWintersClient().search(results, SearchContext(title='foo', encoded='foo', search_site=SITE.name, site_info=SITE))
    assert results == []


@respx.mock
async def test_detail_fields() -> None:
    url = 'https://www.abbywinters.com/scenes/scene-1'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><head><title>abbywinters.com : SubSite : Cool Scene | suffix</title></head><body>
              <div id="shoot-featured-image"><h4>SubSite</h4></div>
              <aside><div class="description">Summary text here. <a>Tag1</a> <a>Tag2</a></div></aside>
            </body></html>""",
        )
    )
    detail = await AbbyWintersClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.studio == 'Abby Winters'
    assert detail.tagline == 'SubSite'
    assert detail.genres == ['Tag1', 'Tag2']
    assert detail.collections == ['SubSite']


@respx.mock
async def test_detail_posters() -> None:
    url = 'https://www.abbywinters.com/scenes/scene-1'
    respx.get(url).mock(
        return_value=httpx.Response(
            200,
            text="""<html><head><title>x : y : z | t</title></head><body>
              <div class="tile-image"><img src="https://cdn.example.com/a.jpg" /></div>
              <div class="video" data-poster="https://cdn.example.com/b.jpg"></div>
            </body></html>""",
        )
    )
    detail = await AbbyWintersClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.raw_image_urls == ['https://cdn.example.com/a.jpg', 'https://cdn.example.com/b.jpg']


def test_is_usable_scene_url() -> None:
    assert __testing__['is_usable_scene_url']('https://abbywinters.com/movies/scene-1') is True
    assert __testing__['is_usable_scene_url']('https://abbywinters.com/nude_girl/jane') is False
    assert __testing__['is_usable_scene_url']('https://abbywinters.com/shoots/cover') is False
    assert __testing__['is_usable_scene_url']('https://abbywinters.com/fetish/x') is False
    assert __testing__['is_usable_scene_url']('https://abbywinters.com/updates/y') is False


def test_strip_locale() -> None:
    assert __testing__['strip_locale']('https://abbywinters.com/en/scene-1') == 'https://abbywinters.com/scene-1'
    assert __testing__['strip_locale']('https://abbywinters.com/de/x') == 'https://abbywinters.com/x'
    assert __testing__['strip_locale']('https://abbywinters.com/scene-1') == 'https://abbywinters.com/scene-1'
