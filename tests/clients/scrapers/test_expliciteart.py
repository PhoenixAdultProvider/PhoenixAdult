from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites.expliciteart import ExpliciteArtClient
from app.registry import find_site

SITE = find_site('Explicite Art')
assert SITE is not None

_SEARCH = """<html><body>
  <div class="content">
    <a href="/visitor/videos/wild-ride.html"><img src="/img/video-thumb.jpg"><div class="vtitle">Wild Ride</div></a>
  </div>
  <div class="content">
    <a href="/visitor/videos/decoy.html"><div class="vtitle">Decoy</div></a>
  </div>
</body></html>"""

_URL = 'https://www.explicite-art.com/visitor/videos/wild-ride.html'
_DETAIL = """<html><head><title>Wild Ride</title></head><body>
  <div class="player-info-desc">A scene description here.</div>
  <span class="tags"><a>Anal</a><a>Hardcore</a></span>
  <div class="player-info-row"><a href="/visitor/models/jane-doe.html">Jane Doe</a></div>
  <div id="player"><script>jwplayer().setup({ image: "https://cdn.example/poster.jpg" });</script></div>
</body></html>"""
_ACTOR = '<html><body><div class="pornstar-bio-left"><img src="https://cdn.example/jane.jpg"></div></body></html>'


@respx.mock
async def test_search_parses_video_cards() -> None:
    respx.get('https://www.explicite-art.com/visitor/search/videos/wild-ride/page1.html').mock(return_value=httpx.Response(200, text=_SEARCH))
    results: list[SearchResult] = []
    await ExpliciteArtClient().search(results, SearchContext(title='Wild Ride', encoded='Wild%20Ride', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Wild Ride'
    assert results[0].scene_url == _URL


@respx.mock
async def test_detail_fields() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, text=_DETAIL))
    respx.get('https://www.explicite-art.com/visitor/models/jane-doe.html').mock(return_value=httpx.Response(200, text=_ACTOR))
    result = await ExpliciteArtClient().fetch_scene_detail(_URL, SITE)
    assert result is not None
    assert result.title == 'Wild Ride'
    assert result.summary == 'A scene description here.'
    assert result.studio == 'Explicite Art'
    assert result.genres == ['Anal', 'Hardcore']
    assert result.actors[0].name == 'Jane Doe'
    assert result.actors[0].photo_url == 'https://cdn.example/jane.jpg'
    assert result.art == ['https://cdn.example/poster.jpg']


def test_registered() -> None:
    from app.clients import CLIENT_REGISTRY

    assert 'expliciteart' in CLIENT_REGISTRY
