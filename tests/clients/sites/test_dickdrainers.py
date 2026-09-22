from __future__ import annotations

import httpx
import pytest
import respx

from phoenixadult.clients.sites import dickdrainers as dd_module
from phoenixadult.clients.sites.dickdrainers import DickDrainersClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site

SITE = find_site('DickDrainers')
assert SITE is not None


@respx.mock
async def test_search_onsite_cards(monkeypatch: pytest.MonkeyPatch, no_web_search: object) -> None:
    monkeypatch.setattr(dd_module, 'web_search_urls', no_web_search)
    url = 'http://dickdrainers.com/tour/search.php?query=wild+scene'
    html = """<html><body>
      <div class="item-video hover">
        <h4><a href="/s/wild-scene.html">Wild Scene</a></h4>
        <div class="date">2021-05-01</div>
      </div>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await DickDrainersClient().search(results, SearchContext(title='wild scene', encoded='wild+scene', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Wild Scene'
    assert results[0].scene_url == 'http://dickdrainers.com/s/wild-scene.html'
    assert results[0].release_date == '2021-05-01'


@respx.mock
async def test_search_web_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    fallback_url = 'http://dickdrainers.com/trailers/extra.html'

    async def _web(*_args: object, **_kwargs: object) -> list[str]:
        return [fallback_url]

    monkeypatch.setattr(dd_module, 'web_search_urls', _web)
    search_url = 'http://dickdrainers.com/tour/search.php?query=extra'
    respx.get(search_url).mock(return_value=httpx.Response(200, text='<html><body></body></html>'))
    detail_html = """<html><body>
      <h3>Extra Scene</h3>
      <div class="videoInfo clear"><p>2020-02-02<span>extra</span></p></div>
    </body></html>"""
    respx.get(fallback_url).mock(return_value=httpx.Response(200, text=detail_html))
    results: list[SearchResult] = []
    await DickDrainersClient().search(results, SearchContext(title='extra', encoded='extra', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Extra Scene'
    assert results[0].scene_url == fallback_url
    assert results[0].release_date == '2020-02-02'


@respx.mock
async def test_detail_fields_genres_actors_images() -> None:
    url = 'http://dickdrainers.com/trailers/wild.html'
    html = """<html><body>
      <h3>Wild Scene</h3>
      <div class="videoDetails clear"><p><span>A blurb.</span><span>FULL VIDEO</span></p></div>
      <div><li>Tags</li><ul><li><a>anal</a></li><li><a>big tits</a></li></ul></div>
      <li class="update_models"><a href="/models/alice.html">Alice</a></li>
      <div class="player_thumbs" src0_3x="https://cdn.dd.com/t0.jpg"><img src0_3x="https://cdn.dd.com/t1.jpg"></div>
      <div class="player full_width"><script>var x = {src0_3x="https://cdn.dd.com/s1.jpg"};</script></div>
    </body></html>"""
    actor_html = '<html><body><div class="profile-pic"><img src0_3x="https://cdn.dd.com/alice.jpg"></div></body></html>'
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    respx.get('http://dickdrainers.com/models/alice.html').mock(return_value=httpx.Response(200, text=actor_html))
    detail = await DickDrainersClient().fetch_scene_detail(f'{url}|2021-05-01', SITE)
    assert detail is not None
    assert detail.title == 'Wild Scene'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'DickDrainers'
    assert detail.release_date == '2021-05-01'
    assert detail.genres == ['Anal', 'Big Tits']
    assert len(detail.actors) == 1
    assert detail.actors[0].name == 'Alice'
    assert detail.actors[0].photo_url == 'https://cdn.dd.com/alice.jpg'
    assert detail.art == ['https://cdn.dd.com/t0.jpg', 'https://cdn.dd.com/t1.jpg', 'https://cdn.dd.com/s1.jpg']


@respx.mock
async def test_detail_actor_slug_fallback() -> None:
    url = 'http://dickdrainers.com/s/big-tit-mindfuck.html'
    html = '<html><body><h3>Big Tit Mindfuck</h3></body></html>'
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    detail = await DickDrainersClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert [a.name for a in detail.actors] == ['Anna Blaze']
