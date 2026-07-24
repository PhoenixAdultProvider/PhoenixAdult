from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.sites.cumbizz import CumbizzClient
from phoenixadult.registry import find_site

SITE = find_site('Cumbizz')
assert SITE is not None

DETAIL_HTML = """<html><body>
  <h1 class="har_h1_title">Wild Film</h1>
  <div class="container text-center"><h2>A blurb.</h2></div>
  <span class="label label-primary"><a>Anal</a></span>
  <span class="label label-primary"><a>POV</a></span>
  <div class="breadcrumbs"><a>Alice</a><a>Bob</a><a>Alice</a></div>
  <section class="har_section har_image_bck" data-image="https://cdn.cb.com/bg.jpg"></section>
  <img class="vidgal unos" src="https://cdn.cb.com/g1.jpg">
  <img class="vidgal dos" src="/g2.jpg">
</body></html>"""


@respx.mock
async def test_search_direct_url_single_result() -> None:
    url = 'https://cumbizz.com/film/wild-film'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    results: list[SearchResult] = []
    await CumbizzClient().search(results, SearchContext(title='wild film', encoded='wild+film', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Wild Film'
    assert results[0].scene_url == 'https://cumbizz.com/film/wild-film'
    assert results[0].score == 90


@respx.mock
async def test_search_returns_empty_when_no_title() -> None:
    url = 'https://cumbizz.com/film/missing'
    respx.get(url).mock(return_value=httpx.Response(200, text='<html><body></body></html>'))
    results: list[SearchResult] = []
    await CumbizzClient().search(results, SearchContext(title='missing', encoded='missing', search_site=SITE.name, site_info=SITE))
    assert results == []


@respx.mock
async def test_detail_fields_genres_actors_images() -> None:
    url = 'https://cumbizz.com/film/wild-film'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    detail = await CumbizzClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Wild Film'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'Cumbizz'
    assert detail.tagline == 'Cumbizz'
    assert detail.collections == ['Cumbizz']
    assert detail.genres == ['anal', 'pov']
    assert [a.name for a in detail.actors] == ['Alice', 'Bob']
    assert detail.art == ['https://cdn.cb.com/bg.jpg', 'https://cdn.cb.com/g1.jpg', 'https://cumbizz.com/g2.jpg']
