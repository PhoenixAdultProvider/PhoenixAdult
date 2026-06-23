from __future__ import annotations

import httpx
import pytest
import respx

import app.clients.aggregators.data18empire as d18e_module
from app.clients.aggregators.data18empire import Data18EmpireClient
from app.clients.base import SearchContext
from app.registry import find_site

SITE = find_site('Data18 Empire')
assert SITE is not None

MOVIE_PAGE = """<html><body>
  <h1 class="description">Big Movie, The</h1>
  <div class="synopsis">A grand description.</div>
  <div class="studio"><a>Empire Studios</a></div>
  <div class="release-date"><span>Released:</span> Jan 5, 2024</div>
  <div class="categories"><a>Anal</a><a>Hardcore</a></div>
  <div class="video-performer">
    <a><img title="Jane Doe" data-bgsrc="https://cdn.example/jane.jpg" /><span><span>Jane Doe</span></span></a>
  </div>
  <div class="item-grid item-grid-scene">
    <div class="grid-item">
      <a href="/scene1"><img src="https://cdn.example/shot1.jpg" /></a>
      <div class="scene-cast-list"><a>Mary Roe</a></div>
    </div>
  </div>
  <div id="video-container-details">
    <div><section><a><picture><source data-srcset="https://cdn.example/cover.jpg" /></picture></a></section></div>
  </div>
</body></html>"""


async def _no_web_search(*_args: object, **_kwargs: object) -> list[str]:
    return []


def _ctx() -> SearchContext:
    return SearchContext(title='', encoded='', search_site=SITE.name, site_info=SITE, scene_id='1234567', full_title='1234567')


@respx.mock
async def test_search_direct_id_split_scene(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(d18e_module, 'web_search', _no_web_search)
    respx.get('https://data18.empirestores.co/1234567').mock(return_value=httpx.Response(200, text=MOVIE_PAGE))
    results = await Data18EmpireClient().search(_ctx())
    assert len(results) == 2
    assert results[0].title == 'The Big Movie'
    assert results[0].score == 100
    assert results[1].title == 'The Big Movie [Scene 1]'


@respx.mock
async def test_detail_movie(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(d18e_module, 'web_search', _no_web_search)
    respx.get('https://data18.empirestores.co/1234567').mock(return_value=httpx.Response(200, text=MOVIE_PAGE))
    client = Data18EmpireClient()
    results = await client.search(_ctx())
    detail = await client.fetch_scene_detail(client.decode(results[0].cur_id), SITE)
    assert detail is not None
    assert detail.title == 'The Big Movie'
    assert detail.summary == 'A grand description.'
    assert detail.studio == 'Empire Studios'
    assert detail.release_date == '2024-01-05'
    assert detail.genres == ['Anal', 'Hardcore']
    assert [(a.name, a.photo_url) for a in detail.actors] == [('Jane Doe', 'https://cdn.example/jane.jpg')]
    assert detail.raw_image_urls == ['https://cdn.example/cover.jpg']


@respx.mock
async def test_detail_split_scene(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(d18e_module, 'web_search', _no_web_search)
    respx.get('https://data18.empirestores.co/1234567').mock(return_value=httpx.Response(200, text=MOVIE_PAGE))
    client = Data18EmpireClient()
    results = await client.search(_ctx())
    detail = await client.fetch_scene_detail(client.decode(results[1].cur_id), SITE)
    assert detail is not None
    assert detail.title == 'The Big Movie [Scene 1]'
    assert [a.name for a in detail.actors] == ['Mary Roe']
    assert 'https://cdn.example/shot1.jpg' in detail.raw_image_urls
