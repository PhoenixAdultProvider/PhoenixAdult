from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.sites.desperateamateurs import DesperateAmateursClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site

SITE = find_site('Desperate Amateurs')
assert SITE is not None


@respx.mock
async def test_search_parses_rows() -> None:
    url = 'https://desperateamateurs.com/fintour/search.php?st=advanced&qall=wild%20scene'
    html = """<html><body>
      <div align="left">
        <a class="update_title" href="thumb">img</a>
        <a class="update_title" href="sets/wild.html">Wild Scene</a>
        <span class="date">Added: 2021-09-12</span>
      </div>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await DesperateAmateursClient().search(results, SearchContext(title='wild scene', encoded='wild%20scene', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Wild Scene'
    assert results[0].scene_url == 'https://desperateamateurs.com/fintour/sets/wild.html'
    assert results[0].release_date == '2021-09-12'


@respx.mock
async def test_detail_fields_actors_genres_images() -> None:
    url = 'https://desperateamateurs.com/fintour/sets/wild.html'
    html = """<html><body>
      <div class="title_bar">Wild Scene</div>
      <div class="gallery_description">A blurb.</div>
      <td class="date">Added: 2021-09-12</td>
      <a href="category/anal">Anal</a>
      <a href="sets/alice.html">Alice</a>
      <div class="gal_block"><img src="https://cdn.da.com/g1.jpg"><img src="g2.jpg"></div>
    </body></html>"""
    actor_html = '<html><body><img class="thumbs" src="alice.jpg"></body></html>'
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    respx.get('https://desperateamateurs.com/fintour/sets/alice.html').mock(return_value=httpx.Response(200, text=actor_html))
    detail = await DesperateAmateursClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Wild Scene'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'Desperate Amateurs'
    assert detail.collections == ['Desperate Amateurs']
    assert detail.release_date == '2021-09-12'
    assert detail.genres == ['Anal']
    assert len(detail.actors) == 1
    assert detail.actors[0].name == 'Alice'
    assert detail.actors[0].photo_url == 'https://desperateamateurs.com/fintour/alice.jpg'
    assert detail.art == ['https://cdn.da.com/g1.jpg', 'https://desperateamateurs.com/fintour/g2.jpg']
