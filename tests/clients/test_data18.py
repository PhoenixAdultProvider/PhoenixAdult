from __future__ import annotations

from datetime import datetime

import httpx
import respx

from app.clients.aggregators.data18 import Data18Client, manual_mapping_url, mapping_slug

_SEARCH = (
    '<html>pages: 1'
    '<a href="/scenes/123-some-title">'
    '<p class="gen12 bold">Some Title</p>'
    '<span class="gen11"><b>#1</b> 2024-01-02 <i>BangBros</i></span>'
    '</a></html>'
)


async def test_manual_mapping_shortcut() -> None:
    # Callers pass the project1-side slug (a dict value); it resolves to the
    # data18 scene id (the key) used in the URL.
    url = await Data18Client().find_scene_url('thats-better-than-stealing-it-herfreshmanyear', 'whatever', [], None)
    assert url == 'https://www.data18.com/scenes/169646'


def test_mapping_slug_matches_the_client_formula() -> None:
    assert mapping_slug('Delicious Firsts', 'Hussie Pass') == 'delicious-firsts-hussiepass'
    assert mapping_slug('Solo Scene', None) == 'solo-scene'
    assert mapping_slug('', 'Whatever') is None


def test_manual_mapping_url_resolves_value_to_key() -> None:
    assert manual_mapping_url('delicious-firsts-hussiepass') == 'https://www.data18.com/scenes/1313219'
    assert manual_mapping_url('not-a-mapped-slug') is None
    assert manual_mapping_url(None) is None


@respx.mock
async def test_find_scene_url_scores_match() -> None:
    respx.route(method='GET', url__regex=r'data18\.com/sys/live\.php').mock(return_value=httpx.Response(200, text=_SEARCH))
    url = await Data18Client().find_scene_url(None, 'Some Title', ['BangBros'], datetime(2024, 1, 2))
    assert url == 'https://www.data18.com/scenes/123-some-title'


@respx.mock
async def test_find_scene_url_rejects_low_accuracy() -> None:
    respx.route(method='GET', url__regex=r'data18\.com/sys/live\.php').mock(return_value=httpx.Response(200, text=_SEARCH))
    # Different provider + title + date → accuracy below the default 100 threshold.
    url = await Data18Client().find_scene_url(None, 'Totally Different', ['OtherStudio'], datetime(2010, 5, 5))
    assert url is None


@respx.mock
async def test_find_scene_url_retries_with_digit_title() -> None:
    digit_search = _SEARCH.replace('Some Title', 'World War XXX: Part 2').replace('/scenes/123-some-title', '/scenes/456-ww-xxx-part-2')
    respx.route(method='GET', url__regex=r'data18\.com/sys/live\.php').mock(return_value=httpx.Response(200, text=digit_search))
    url = await Data18Client().find_scene_url(None, 'World War XXX: Part Two', ['BangBros'], datetime(2024, 1, 2))
    assert url == 'https://www.data18.com/scenes/456-ww-xxx-part-2'


@respx.mock
async def test_fetch_images_poster_only() -> None:
    scene = '<html><div id="galleriesoff"></div><div id="moviewrap"><img src="https://cdn.example/poster.jpg"></div></html>'
    respx.route(method='GET', url__regex=r'data18\.com/scenes/').mock(return_value=httpx.Response(200, text=scene))
    imgs = await Data18Client().fetch_images('https://www.data18.com/scenes/123-x')
    assert imgs == ['https://cdn.example/poster.jpg']
