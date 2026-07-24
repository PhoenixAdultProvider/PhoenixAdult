from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.sites.firstanalquest import FirstAnalQuestClient
from phoenixadult.registry import find_site

SITE = find_site('First Anal Quest')
assert SITE is not None


@respx.mock
async def test_search_parses_thumb_cards() -> None:
    url = 'http://www.firstanalquest.com/search/?q=quest'
    html = """<html><body>
      <li class="thumb">
        <a class="thumb-img" href="/scene/quest-1"></a>
        <span class="thumb-title">Quest One</span>
        <span class="thumb-added">2021-02-02</span>
      </li>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await FirstAnalQuestClient().search(results, SearchContext(title='quest', encoded='quest', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Quest One'
    assert results[0].scene_url == 'http://www.firstanalquest.com/scene/quest-1'
    assert results[0].release_date == '2021-02-02'


@respx.mock
async def test_detail_fields_actors_genres_images() -> None:
    url = 'http://www.firstanalquest.com/scene/quest-1'
    html = """<html><body>
      <div class="container content"><div class="page-header"><span class="title">Quest One</span></div></div>
      <div class="text-desc">A blurb.</div>
      <div class="media-body"><ul>Categories <li><a>Anal</a></li><li><a>Teen</a></li></ul></div>
      <ul>Models: <li><a href="/model/alice">Alice</a></li><li><a href="/model/bob">Bob</a></li><li><a href="/model/carol">Carol</a></li></ul>
      <img class="player-preview" src="https://cdn.faq.com/p.jpg">
      <a class="fancybox img-album" href="/g1.jpg">x</a>
      <a data-fancybox-group="gallery" href="https://cdn.faq.com/g2.jpg">x</a>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    for slug in ('alice', 'bob', 'carol'):
        actor_html = f'<html><body><div class="model-box"><img src="https://cdn.faq.com/{slug}.jpg"></div></body></html>'
        respx.get(f'http://www.firstanalquest.com/model/{slug}').mock(return_value=httpx.Response(200, text=actor_html))
    detail = await FirstAnalQuestClient().fetch_scene_detail(f'{url}|2021-02-02', SITE)
    assert detail is not None
    assert detail.title == 'Quest One'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'Pioneer'
    assert detail.collections == ['First Anal Quest']
    assert detail.release_date == '2021-02-02'
    assert detail.genres == ['Anal', 'Teen', 'Threesome']
    assert [a.name for a in detail.actors] == ['Alice', 'Bob', 'Carol']
    assert detail.actors[0].photo_url == 'https://cdn.faq.com/alice.jpg'
    assert detail.art == ['https://cdn.faq.com/p.jpg', 'http://www.firstanalquest.com/g1.jpg', 'https://cdn.faq.com/g2.jpg']
