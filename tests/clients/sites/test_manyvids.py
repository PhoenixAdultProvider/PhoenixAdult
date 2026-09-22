from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.sites.manyvids import ManyvidsClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site
from phoenixadult.utils.helpers.ids import pack_cur_id

SITE = find_site('ManyVids')
assert SITE is not None

LDJSON = '{"name": "Solo Show", "uploadDate": "2021-08-08"}'
SCENE_HTML = f'<html><head><script type="application/ld+json">{LDJSON}</script></head><body></body></html>'

API_BODY = {
    'data': {
        'title': 'Solo Show',
        'description': 'A blurb.',
        'model': {'displayName': 'Alice', 'avatar': 'https://cdn.mv.com/alice.jpg'},
        'tagList': [{'label': 'Solo'}, {'label': 'Toys'}],
        'screenshot': 'https://cdn.mv.com/shot.jpg',
    }
}


@respx.mock
async def test_search_ldjson() -> None:
    url = 'https://www.manyvids.com/video/12345'
    respx.get(url).mock(return_value=httpx.Response(200, text=SCENE_HTML))
    results: list[SearchResult] = []
    await ManyvidsClient().search(results, SearchContext(title='12345', encoded='12345', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Solo Show'
    assert results[0].scene_url == url
    assert results[0].score == 100
    assert results[0].release_date == '2021-08-08'


@respx.mock
async def test_detail_json_api() -> None:
    scene_url = 'https://www.manyvids.com/video/12345-solo-show'
    respx.get('https://www.manyvids.com/bff/store/video/12345').mock(return_value=httpx.Response(200, json=API_BODY))
    cur_id = pack_cur_id([scene_url, '2021-08-08'])
    detail = await ManyvidsClient().fetch_scene_detail(ManyvidsClient().decode(cur_id), SITE)
    assert detail is not None
    assert detail.title == 'Solo Show'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'ManyVids'
    assert detail.tagline == 'Alice'
    assert detail.collections == ['Alice']
    assert detail.release_date == '2021-08-08'
    assert detail.genres == ['Solo', 'Toys']
    assert [a.name for a in detail.actors] == ['Alice']
    assert detail.actors[0].photo_url == 'https://cdn.mv.com/alice.jpg'
    assert detail.art == ['https://cdn.mv.com/shot.jpg']
