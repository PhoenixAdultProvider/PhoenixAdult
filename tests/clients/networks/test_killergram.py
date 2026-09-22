from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.networks.killergram import KillergramClient
from phoenixadult.models.scrape import SearchResult
from phoenixadult.registry import find_site
from tests.support import search_context

SITE = find_site('Killergram')
assert SITE is not None

_PAGE = """<html><body>
  <img id="episode_001" src="https://media.killergram.com/models/Jane Doe/Jane Doe_Cool Scene/1.jpg" />
  <img id="episode_002" src="https://media.killergram.com/models/Jane Doe/Jane Doe_Cool Scene/2.jpg" />
  <div><span class="episodeheader">published</span> 12 May 2024</div>
  <div><span class="episodeheader">starring</span><span class="modelstarring"><a>Jane Doe</a></span></div>
  <table class="episodetext"><tr><td>x</td></tr><tr><td>x</td></tr><tr><td>x</td></tr><tr><td>x</td></tr><tr><td>l</td><td>A summary.</td></tr></table>
</body></html>"""


@respx.mock
async def test_search() -> None:
    url = 'https://killergram.com/episodes.asp?page=episodes&id=123'
    respx.get(url).mock(return_value=httpx.Response(200, text=_PAGE))
    results: list[SearchResult] = []
    await KillergramClient().search(results, search_context(SITE, '123', space=' '))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].score == 100
    assert results[0].display_date == '2024-05-12'


@respx.mock
async def test_detail() -> None:
    url = 'https://killergram.com/episodes.asp?page=episodes&id=123'
    respx.get(url).mock(return_value=httpx.Response(200, text=_PAGE))
    detail = await KillergramClient().fetch_scene_detail('123', SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Killergram'
    assert detail.tagline == 'Killergram'
    assert detail.release_date == '2024-05-12'
    assert detail.genres == ['British']
    assert [a.name for a in detail.actors] == ['Jane Doe']
    assert detail.art == [
        'https://media.killergram.com/models/Jane Doe/Jane Doe_Cool Scene/1.jpg',
        'https://media.killergram.com/models/Jane Doe/Jane Doe_Cool Scene/2.jpg',
    ]
