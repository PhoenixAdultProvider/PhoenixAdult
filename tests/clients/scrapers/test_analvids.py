from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext
from app.clients.sites.analvids import AnalVidsClient
from app.registry import find_site

SITE = find_site('AnalVids')
assert SITE is not None

DETAIL_HTML = """<html><body>
  <h1 class="watch__title">Deep Scene featuring Alice</h1>
  <div class="text-mob-more">A blurb.</div>
  <div class="genres-list">
    <a href="/studio/legalporno">LegalPorno</a>
    <a href="/genre/anal">Anal</a>
    <a href="/genre/gonzo">Gonzo</a>
  </div>
  <i class="bi-calendar3">2021-08-20</i>
  <a href="/model/alice">Alice</a>
  <a href="/forum/model/bob">Bob</a>
  <div class="watch__video"><video data-poster="https://cdn.av.com/poster.jpg"></video></div>
</body></html>"""

ACTOR_HTML = '<html><body><div class="model"><img src="https://cdn.av.com/alice.jpg"></div></body></html>'


@respx.mock
async def test_search_json_api() -> None:
    api = 'https://analvids.com/api/autocomplete/search?q=deep%20scene'
    payload = {
        'terms': [
            {'type': 'scene', 'name': 'Deep Scene', 'url': 'https://analvids.com/watch/123', 'source_id': 123},
            {'type': 'model', 'name': 'Alice', 'url': 'https://analvids.com/model/alice'},
        ]
    }
    respx.get(api).mock(return_value=httpx.Response(200, json=payload))
    results = await AnalVidsClient().search(SearchContext(title='123 deep scene', encoded='', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Deep Scene'
    assert results[0].scene_url == 'https://analvids.com/watch/123'
    assert results[0].score == 100  # leading numeric token matched source_id


@respx.mock
async def test_detail_fields_actors_genres_poster() -> None:
    url = 'https://analvids.com/watch/123'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    respx.get('https://analvids.com/model/alice').mock(return_value=httpx.Response(200, text=ACTOR_HTML))
    detail = await AnalVidsClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Deep Scene'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'AnalVids'
    assert detail.tagline == 'LegalPorno'
    assert detail.collections == ['LegalPorno']
    assert detail.release_date == '2021-08-20'
    assert detail.genres == ['Anal', 'Gonzo']
    assert [a.name for a in detail.actors] == ['Alice']  # forum link excluded
    assert detail.actors[0].photo_url == 'https://cdn.av.com/alice.jpg'
    assert detail.raw_image_urls == ['https://cdn.av.com/poster.jpg']
