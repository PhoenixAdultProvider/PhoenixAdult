from __future__ import annotations

import httpx
import pytest
import respx

from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.sites.momcomesfirst import MomComesFirstClient
from phoenixadult.registry import find_site

SITE = find_site('Mom Comes First')
assert SITE is not None


@respx.mock
async def test_search_strips_relationship_words() -> None:
    url = 'https://momcomesfirst.com/?s=secret+lesson'
    html = """<html><body>
      <article>
        <h2><a href="/scene/secret-lesson">Secret Lesson</a></h2>
        <p><span>Mar 3, 2021</span></p>
      </article>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await MomComesFirstClient().search(results, SearchContext(title='moms sons secret lesson', encoded='', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Secret Lesson'
    assert results[0].scene_url == 'https://momcomesfirst.com/scene/secret-lesson'
    assert results[0].release_date == '2021-03-03'


@respx.mock
async def test_search_strips_actor_prefix_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('SEARCH_STRIP_ACTORS', SITE.name)
    url = 'https://momcomesfirst.com/?s=secret+lesson'
    respx.get(url).mock(
        return_value=httpx.Response(200, text='<html><body><article><h2><a href="/scene/secret-lesson">Secret Lesson</a></h2></article></body></html>')
    )
    results: list[SearchResult] = []
    await MomComesFirstClient().search(results, SearchContext(title='cory chase moms secret lesson', encoded='', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Secret Lesson'


@respx.mock
async def test_detail_genres_actors_split() -> None:
    url = 'https://momcomesfirst.com/scene/secret-lesson'
    html = """<html><body>
      <h1>Secret Lesson</h1>
      <div class="entry-content">
        <p>A blurb.</p>
        <p>Starring Cory Chase & Alex Adams *exclusive</p>
      </div>
      <span class="published">Mar 3, 2021</span>
      <a rel="tag">taboo</a>
      <a rel="tag">cory chase</a>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    detail = await MomComesFirstClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Secret Lesson'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'Mom Comes First'
    assert detail.release_date == '2021-03-03'
    assert detail.genres == ['Taboo']
    assert [a.name for a in detail.actors] == ['Cory Chase', 'Alex Adams']
