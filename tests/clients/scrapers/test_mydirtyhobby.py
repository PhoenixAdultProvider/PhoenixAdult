from __future__ import annotations

import json

import httpx
import respx

from app.clients.base import SearchContext
from app.clients.sites.mydirtyhobby import MyDirtyHobbyClient
from app.registry import find_site

SITE = find_site('My Dirty Hobby')
assert SITE is not None

SEARCH_API = 'https://www.mydirtyhobby.com/content/api/v2/global-search/video'
SEARCH_BODY = {
    'items': [
        {'contentType': 'video', 'title': 'Homemade Fun', 'u_id': '7', 'nick': 'lola', 'uv_id': '99', 'onlineAt': '03/04/21'},
        {'contentType': 'profile', 'title': 'lola'},
    ]
}

DETAIL_JSON = {
    'content': {
        'title': {'text': 'Homemade Fun'},
        'description': {'text': 'A blurb.'},
        'subtitle': {'text': '2021-04-03'},
        'categories': {'items': [{'text': 'Amateur'}, {'text': 'POV'}]},
        'videoNotPurchased': {'thumbnail': {'src': 'https://cdn.mdh.com/poster.jpg'}},
    },
    'profileHeader': {'profileAvatar': {'title': 'Lola', 'thumbImg': {'src': 'https://cdn.mdh.com/lola.jpg'}}},
}
DETAIL_HTML = f'<html><body><div><div id="profile_page"></div><script>window.__DATA__ = {json.dumps(DETAIL_JSON)};</script></div></body></html>'


@respx.mock
async def test_search_json_post() -> None:
    respx.post(SEARCH_API).mock(return_value=httpx.Response(200, json=SEARCH_BODY))
    results = await MyDirtyHobbyClient().search(SearchContext(title='homemade', encoded='homemade', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1  # only the video item
    assert results[0].title == 'Homemade Fun'
    assert results[0].scene_url == 'https://www.mydirtyhobby.com/profil/7-lola/videos/99-Homemade-Fun'
    assert results[0].release_date == '2021-04-03'


@respx.mock
async def test_detail_embedded_json() -> None:
    url = 'https://www.mydirtyhobby.com/profil/7-lola/videos/99-Homemade-Fun'
    respx.get(url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    detail = await MyDirtyHobbyClient().fetch_scene_detail(url, SITE)
    assert detail is not None
    assert detail.title == 'Homemade Fun'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'My Dirty Hobby'
    assert detail.tagline == 'Lola'
    assert detail.collections == ['Lola']
    assert detail.release_date == '2021-04-03'
    assert detail.genres == ['amateur', 'pov']
    assert [a.name for a in detail.actors] == ['Lola']
    assert detail.actors[0].photo_url == 'https://cdn.mdh.com/lola.jpg'
    assert detail.raw_image_urls == ['https://cdn.mdh.com/poster.jpg']
