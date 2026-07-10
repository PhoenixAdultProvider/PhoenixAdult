from __future__ import annotations

import pytest
from parsel import Selector

import app.utils.images.fansite_adapters  # noqa: F401 - registers the adapters
from app.utils.images import fanart
from app.utils.images.fanart import FindFanArtOptions, find_fan_art, register_fanart_overrides

_IMAGEPOST = """<html>
  <h1>Jane Doe Scene</h1>
  <h3><a href="/star/jane">Jane Doe</a></h3>
  <div id="theGallery"><a href="https://img.example/1.jpg">1</a><a href="https://img.example/2.jpg">2</a></div>
  <div class="central-section-content"><p>Summary text</p></div>
</html>"""

_XARTBEAUTIES = """<html>
  <div id="header-text"><p>Jane Doe Gallery</p></div>
  <a href="/models/jane">Jane Doe</a>
  <a href="/models/all">Models</a>
  <div id="gallery-thumbs"><img src="https://images.example/tn1.jpg"></div>
</html>"""


def _page(html: str):
    async def fetch_page(url: str) -> Selector:
        return Selector(text=html)

    return fetch_page


def _search(urls: list[str]):
    async def web_search(query: str, domain: str, limit: int) -> list[str]:
        return urls

    return web_search


@pytest.fixture(autouse=True)
def reset_overrides() -> None:
    fanart.__testing__['reset_overrides']()


def test_all_adapters_registered() -> None:
    assert fanart.__testing__['fansite_count']() == 16


async def test_find_fan_art_imagepost() -> None:
    result = await find_fan_art(
        FindFanArtOptions(
            sites=['ImagePost.com'],
            title='Jane Doe Scene',
            actor_names=['Jane Doe'],
            fetch_page=_page(_IMAGEPOST),
            web_search=_search(['http://imagepost.com/jane-doe-scene']),
        )
    )
    assert result.source == 'ImagePost.com'
    assert result.images == ['https://img.example/1.jpg', 'https://img.example/2.jpg']
    assert result.summary == 'Summary text'


async def test_contains_filter_excludes_models_link() -> None:
    result = await find_fan_art(
        FindFanArtOptions(
            sites=['XartBeauties.com'],
            title='Jane Doe',
            actor_names=['Jane Doe'],
            fetch_page=_page(_XARTBEAUTIES),
            web_search=_search(['http://xartbeauties.com/jane']),
        )
    )
    assert result.source == 'XartBeauties.com'
    assert len(result.images) == 1


async def test_actor_gate_rejects_wrong_actor() -> None:
    result = await find_fan_art(
        FindFanArtOptions(
            sites=['ImagePost.com'],
            title='Jane Doe Scene',
            actor_names=['Someone Else'],
            fetch_page=_page(_IMAGEPOST),
            web_search=_search(['http://imagepost.com/x']),
        )
    )
    assert result.images == []


async def test_no_match_override_skips() -> None:
    register_fanart_overrides(no_match=['Jane Doe Scene'])
    result = await find_fan_art(
        FindFanArtOptions(
            sites=['ImagePost.com'],
            title='Jane Doe Scene',
            actor_names=['Jane Doe'],
            fetch_page=_page(_IMAGEPOST),
            web_search=_search(['http://imagepost.com/x']),
        )
    )
    assert result.images == []


async def test_bad_match_override_pins_and_skips_gates() -> None:
    register_fanart_overrides(bad_match=[{'title': 'Special', 'site': 'ImagePost.com', 'url': 'http://imagepost.com/special'}])
    result = await find_fan_art(
        FindFanArtOptions(
            sites=['SomewhereElse.com'],
            title='Special',
            actor_names=['Whoever'],
            fetch_page=_page(_IMAGEPOST),
            web_search=_search([]),
        )
    )
    assert result.source == 'ImagePost.com'
    assert result.images == ['https://img.example/1.jpg', 'https://img.example/2.jpg']
