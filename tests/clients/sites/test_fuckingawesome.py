from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.sites.fuckingawesome import FuckingAwesomeClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site

SITE = find_site('FuckingAwesome')
assert SITE is not None


@respx.mock
async def test_search_parses_gallery_cards() -> None:
    url = 'https://fuckingawesome.com/search/videos/awesome'
    html = """<html><body>
      <div class="gallery"><div>
        <div class="video-title truncate"><a href="/scene/awesome-1">Awesome One</a></div>
        <span class="small date">2021-01-15</span>
      </div></div>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await FuckingAwesomeClient().search(results, SearchContext(title='awesome', encoded='awesome', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Awesome One'
    assert results[0].scene_url == 'https://fuckingawesome.com/scene/awesome-1'
    assert results[0].release_date == '2021-01-15'


@respx.mock
async def test_detail_fields_actors_genres_images() -> None:
    url = 'https://fuckingawesome.com/scene/awesome-1'
    html = """<html><body>
      <h1>Awesome One</h1>
      <div class="more text-justify">A blurb.</div>
      <div class="videodate"><strong>January 15, 2021</strong></div>
      <div class="tags"><ul><li><a>Anal</a></li><li><a>HD</a></li></ul></div>
      <div class="pornstarnames"><ul>
        <li><a href="/pornstars/alice">Alice</a></li>
        <li><a href="/pornstars/bob">Bob</a></li>
        <li><a href="/pornstars/carol">Carol</a></li>
      </ul></div>
      <span class="et_pb_image_wrap"><img content="https://cdn.fa.com/p1.jpg"></span>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    for slug in ('alice', 'bob', 'carol'):
        actor_html = f'<html><body><div class="pornstar-pic"><img src="https://cdn.fa.com/{slug}.jpg"></div></body></html>'
        respx.get(f'https://fuckingawesome.com/pornstars/{slug}').mock(return_value=httpx.Response(200, text=actor_html))
    detail = await FuckingAwesomeClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Awesome One'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'FuckingAwesome'
    assert detail.release_date == '2021-01-15'
    assert detail.genres == ['anal', 'hd', 'Threesome']
    assert [a.name for a in detail.actors] == ['Alice', 'Bob', 'Carol']
    assert detail.actors[0].photo_url == 'https://cdn.fa.com/alice.jpg'
    assert detail.art == ['https://cdn.fa.com/p1.jpg']
