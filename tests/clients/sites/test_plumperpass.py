from __future__ import annotations

import httpx
import pytest
import respx

from phoenixadult.clients.sites import plumperpass as pp_module
from phoenixadult.clients.sites.plumperpass import PlumperPassClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site

SITE = find_site('PlumperPass')
assert SITE is not None

CONTENT_URL = 'https://plumperpass.com/t1/hsp/2222/content.html'

DETAIL_HTML = """<html><body>
  <h2 class="vidtitle">"Big Fun"</h2>
  <div class="vidinfo"><p>A blurb.</p></div>
  <p class="tags clearfix"><a>BBW</a><a>Hardcore</a></p>
  <h3 class="releases">June 6, 2021<br><a href="model.php?id=1">Alice</a></h3>
  <div class="movie-big"><script>var p = {image: "img/poster.jpg"};</script></div>
  <div class="movie-trailer"><img src="img/t1.jpg"></div>
</body></html>"""

ACTOR_HTML = '<html><body><div class="row mainrow"><img src="img/alice.jpg"></div></body></html>'


async def _no_web(*_a: object, **_k: object) -> list[str]:
    return []


@respx.mock
async def test_search_refstat_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pp_module, 'web_search_urls', _no_web)
    ref = 'https://plumperpass.com/t1/refstat.php?lid=2222&sid=584'
    respx.get(ref).mock(return_value=httpx.Response(302, headers={'Location': CONTENT_URL}))
    respx.get(CONTENT_URL).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    results: list[SearchResult] = []
    await PlumperPassClient().search(results, SearchContext(title='big fun', encoded='big+fun', search_site=SITE.name, site_info=SITE, scene_id='2222'))
    assert len(results) == 1
    assert results[0].title == 'Big Fun'
    assert results[0].scene_url == CONTENT_URL
    assert results[0].release_date == '2021-06-06'


@respx.mock
async def test_detail_tagline_genres_actors_images() -> None:
    respx.get(CONTENT_URL).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    respx.get('https://plumperpass.com/t1/model.php?id=1').mock(return_value=httpx.Response(200, text=ACTOR_HTML))
    detail = await PlumperPassClient().fetch_scene_detail(f'{CONTENT_URL}|2021-06-06', SITE)
    assert detail is not None
    assert detail.title == 'Big Fun'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'PlumperPass'
    assert detail.tagline == 'Hot Sexy Plumpers'
    assert detail.collections == ['Hot Sexy Plumpers']
    assert detail.release_date == '2021-06-06'
    assert detail.genres == ['BBW', 'Hardcore']
    assert [a.name for a in detail.actors] == ['Alice']
    assert detail.actors[0].photo_url == 'https://plumperpass.com/t1/img/alice.jpg'
    assert detail.art == ['https://plumperpass.com/t1/img/poster.jpg', 'https://plumperpass.com/t1/img/t1.jpg']
