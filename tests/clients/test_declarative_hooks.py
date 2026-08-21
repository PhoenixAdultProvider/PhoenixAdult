from __future__ import annotations

from typing import Any

import pytest
from parsel import Selector

from phoenixadult.clients.base import Client, LoadedScene, SceneDetail

_PAGE = """
<html><body>
  <h1>A Wild Scene</h1>
  <div class="desc">Some blurb.</div>
  <div class="cats"><a>Anal</a><a>POV</a><a>Anal</a></div>
  <div class="cast"><a>Jane Doe</a><a>John Roe</a></div>
</body></html>
"""


class _Declared(Client):
    title_xpath = '//h1'
    summary_xpath = '//div[@class="desc"]'
    genres_xpath = '//div[@class="cats"]//a'
    actors_xpath = '//div[@class="cast"]//a'


class _Silent(Client):
    pass


def _scene() -> Any:
    return LoadedScene(sel=Selector(text=_PAGE), site=None, url='', capture=None)  # type: ignore[arg-type]


async def test_declared_xpaths_fill_every_field() -> None:
    detail = SceneDetail()
    scene = _scene()
    client = _Declared()
    await client.fetch_title(scene, detail)
    await client.fetch_summary(scene, detail)
    await client.fetch_genres(scene, detail)
    await client.fetch_actors(scene, detail)

    assert detail.title == 'A Wild Scene'
    assert detail.summary == 'Some blurb.'
    assert detail.genres == ['Anal', 'POV'], 'the base default must dedupe like the hand-written versions did'
    assert [a.name for a in detail.actors] == ['Jane Doe', 'John Roe']


@pytest.mark.parametrize('hook', ['fetch_title', 'fetch_summary', 'fetch_genres', 'fetch_actors'])
async def test_a_client_that_declares_nothing_is_left_untouched(hook: str) -> None:
    detail = SceneDetail(title='kept', summary='kept')
    before = (detail.title, detail.summary, list(detail.genres or []), list(detail.actors or []))
    await getattr(_Silent(), hook)(_scene(), detail)
    assert (detail.title, detail.summary, list(detail.genres or []), list(detail.actors or [])) == before


async def test_a_missing_node_yields_empty_not_an_error() -> None:
    class _Missing(Client):
        title_xpath = '//nope'

    detail = SceneDetail(title='old')
    await _Missing().fetch_title(_scene(), detail)
    assert detail.title == ''


async def test_several_xpaths_are_tried_in_order() -> None:
    class _Fallback(Client):
        title_xpath = ('//h2', '//h1')

    detail = SceneDetail()
    await _Fallback().fetch_title(_scene(), detail)
    assert detail.title == 'A Wild Scene', 'the first xpath that yields text wins'


async def test_a_tuple_that_matches_nothing_yields_empty() -> None:
    class _NoneMatch(Client):
        summary_xpath = ('//nope', '//also-nope')

    detail = SceneDetail(summary='old')
    await _NoneMatch().fetch_summary(_scene(), detail)
    assert detail.summary == ''


def test_search_rows_is_declarative_too() -> None:
    class _Rows(Client):
        search_rows_xpath = '//div[@class="row"]'

    assert _Rows().search_rows_xpath == '//div[@class="row"]'
    assert Client.search_rows_xpath is None, 'a client that declares nothing keeps the old no-op behavior'
