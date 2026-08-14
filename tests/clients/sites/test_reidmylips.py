from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.sites.reidmylips import ReidMyLipsClient
from phoenixadult.registry import find_site

SITE = find_site('ReidMyLips')
assert SITE is not None

DETAIL_HTML = """<html><body>
  <span class="update_title">Lip Service</span>
  <span class="latest_update_description">A blurb.</span>
  <span class="availdate">2021-02-02</span>
  <span class="update_tags"><a>POV</a><a>Blowjob</a></span>
  <div class="update_image"><img src0_2x="https://cdn.rml.com/p1.jpg"></div>
</body></html>"""


@respx.mock
async def test_search_direct_slug() -> None:
    url = 'https://www.reidmylips.com/updates/lip-service.html'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    results: list[SearchResult] = []
    await ReidMyLipsClient().search(results, SearchContext(title='Lip Service', encoded='', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Lip Service'
    assert results[0].scene_url == url
    assert results[0].score == 100
    assert results[0].release_date == '2021-02-02'


@respx.mock
async def test_detail_fields() -> None:
    url = 'https://www.reidmylips.com/updates/lip-service.html'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    detail = await ReidMyLipsClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Lip Service'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'ReidMyLips'
    assert detail.collections == ['ReidMyLips']
    assert detail.release_date == '2021-02-02'
    assert detail.genres == ['POV', 'Blowjob']
    assert [a.name for a in detail.actors] == ['Riley Reid']
    assert detail.art == ['https://cdn.rml.com/p1.jpg']
