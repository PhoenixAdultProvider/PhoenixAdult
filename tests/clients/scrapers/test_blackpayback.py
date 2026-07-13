from __future__ import annotations

import httpx
import pytest
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites import blackpayback as bpb_module
from app.clients.sites.blackpayback import BlackPayBackClient
from app.registry import find_site

SITE = find_site('Black PayBack')
assert SITE is not None

IAFD_STUDIO_HTML = """<html><body>
  <table id="studio"><tbody>
    <tr><td><a href="/title.rme/title=123/birfday-bitch.htm">Birfday Bitch (2021)</a></td></tr>
  </tbody></table>
</body></html>"""

IAFD_SCENE_HTML = """<html><body>
  <p>Release Date</p><p class="biodata">Mar 14, 2021</p>
  <div class="castbox"><a>Aria Carson<img src="https://cdn.iafd.com/aria.jpg"></a></div>
</body></html>"""

DETAIL_HTML = """<html><body>
  <h1>ARIA CARSON 2</h1>
  <div class="videoDetails clear"><p>A blurb.</p></div>
  <div class="featuring clear"><ul><li><a>Anal</a></li><li><a>BBC</a></li><li>noLink</li></ul></div>
  <div class="player"><script>var p = {poster="/poster.jpg"};</script></div>
</body></html>"""


def _mock_iafd() -> None:
    respx.get('https://www.iafd.com/studio.rme/studio=9856/blackpayback.com.htm').mock(return_value=httpx.Response(200, text=IAFD_STUDIO_HTML))
    respx.get('https://www.iafd.com/title.rme/title=123/birfday-bitch.htm').mock(return_value=httpx.Response(200, text=IAFD_SCENE_HTML))


@respx.mock
async def test_search_direct_candidate(monkeypatch: pytest.MonkeyPatch, no_web_search: object) -> None:
    monkeypatch.setattr(bpb_module, 'web_search_urls', no_web_search)
    url = 'https://blackpayback.com/tour/trailers/birfday-bitch.html'
    respx.get(url).mock(return_value=httpx.Response(200, text='<html><body><h1>Birfday Bitch</h1></body></html>'))
    results: list[SearchResult] = []
    await BlackPayBackClient().search(results, SearchContext(title='12 birfday bitch', encoded='', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Birfday Bitch'
    assert results[0].scene_url == url


@respx.mock
async def test_detail_title_fix_iafd_genres_images() -> None:
    url = 'https://blackpayback.com/tour/trailers/birfday-bitch.html'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    _mock_iafd()
    detail = await BlackPayBackClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Birfday Bitch'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'Black PayBack'
    assert detail.collections == ['Black PayBack']
    assert detail.release_date == '2021-03-14'
    assert detail.genres == ['Anal', 'BBC']
    assert [a.name for a in detail.actors] == ['Aria Carson']
    assert detail.actors[0].photo_url == 'https://cdn.iafd.com/aria.jpg'
    assert detail.art == ['https://blackpayback.com/poster.jpg']
