from __future__ import annotations

import json

import httpx
import respx

from phoenixadult.clients.sites.povr import POVRClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site
from phoenixadult.utils.helpers.ids import pack_cur_id

SITE = find_site('POVR')
assert SITE is not None

LD = {
    'name': 'VR Encounter',
    'description': 'A blurb.',
    'uploadDate': '2021-07-07',
    'thumbnailUrl': 'https://cdn.povr.com/tiny/cover.jpg',
    'actor': [{'name': 'Alice', '@id': 'https://povr.com/pornstars/alice'}],
}
DETAIL_HTML = f"""<html><head><script type="application/ld+json">{json.dumps(LD)}</script></head><body>
  <ul class="category-link mb-2"><li><a>VR</a></li><li><a>POV</a></li></ul>
</body></html>"""
ACTOR_HTML = '<html><head><script type="application/ld+json">{"image": "https://cdn.povr.com/alice.jpg"}</script></head><body></body></html>'


@respx.mock
async def test_search_cards() -> None:
    url = 'https://povr.com/search?q=encounter'
    html = """<html><body>
      <div class="thumbnail-wrap"><div>
        <h6 class="thumbnail__title">VR Encounter</h6>
        <a class="thumbnail__link" href="/scene/vr-encounter">x</a>
        <a class="thumbnail__footer-link">POVR Originals</a>
      </div></div>
    </body></html>"""
    respx.get(url).mock(return_value=httpx.Response(200, text=html))
    results: list[SearchResult] = []
    await POVRClient().search(results, SearchContext(title='encounter', encoded='encounter', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'VR Encounter'
    assert results[0].scene_url == 'https://povr.com/scene/vr-encounter'
    assert results[0].subsite == 'POVR Originals'


@respx.mock
async def test_detail_ldjson() -> None:
    scene_url = 'https://povr.com/scene/vr-encounter'
    respx.get(scene_url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    respx.get('https://povr.com/pornstars/alice').mock(return_value=httpx.Response(200, text=ACTOR_HTML))
    cur_id = pack_cur_id([scene_url, 'BadoinkVR'])
    detail = await POVRClient().fetch_scene_detail(POVRClient().decode(cur_id), SITE)
    assert detail is not None
    assert detail.title == 'VR Encounter'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'BadoinkVR'
    assert detail.collections == ['BadoinkVR']
    assert detail.release_date == '2021-07-07'
    assert detail.genres == ['vr', 'pov']
    assert [a.name for a in detail.actors] == ['Alice']
    assert detail.actors[0].photo_url == 'https://cdn.povr.com/alice.jpg'
    assert detail.art == ['https://cdn.povr.com/large/cover.jpg']
