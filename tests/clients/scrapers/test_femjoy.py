from __future__ import annotations

import httpx
import respx

from app.clients.base import SearchContext, SearchResult
from app.clients.sites.femjoy import FemjoyClient
from app.registry import find_site
from app.utils.helpers.helpers import pack_cur_id

SITE = find_site('Femjoy')
assert SITE is not None

SEARCH_URL = 'https://femjoy.com/api/v2/search/videos?include=actors,directors&thumb_size=850x463&query=mirror'

PAYLOAD = {
    'results': [
        {
            'id': 42,
            'title': 'Girl In The Mirror',
            'release_date': '2021-03-12',
            'long_description': '<p>A <b>blurb</b>.</p>',
            'actors': [
                {'id': 1, 'name': 'Maria Rya', 'thumb': {'image': 'https://cdn.fj.com/maria.jpg'}},
                {'id': 2, 'name': 'Bella', 'thumb': {'image': 'https://cdn.fj.com/noimageavailable.gif'}},
                {'id': 3, 'name': 'Cara', 'thumb': {'image': 'https://cdn.fj.com/cara.jpg'}},
            ],
            'directors': [{'name': 'Dir One'}],
            'thumb': {'image': 'https://cdn.fj.com/poster.jpg'},
        }
    ]
}

ACTOR_LOOKUP = 'https://femjoy.com/api/v2/search/actors?thumb_size=355x475&query=Bella'
ACTOR_PAYLOAD = {'results': [{'id': 2, 'thumb': {'image': 'https://cdn.fj.com/bella-real.jpg'}}]}


@respx.mock
async def test_search_json_api() -> None:
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json=PAYLOAD))
    results: list[SearchResult] = []
    await FemjoyClient().search(results, SearchContext(title='mirror', encoded='mirror', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'Girl In The Mirror'
    assert results[0].scene_url == SEARCH_URL
    assert results[0].release_date == '2021-03-12'


@respx.mock
async def test_detail_via_packed_curid() -> None:
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json=PAYLOAD))
    respx.get(ACTOR_LOOKUP).mock(return_value=httpx.Response(200, json=ACTOR_PAYLOAD))
    cur_id = pack_cur_id([SEARCH_URL, '2021-03-12|42'])
    detail = await FemjoyClient().fetch_scene_detail(FemjoyClient().decode(cur_id), SITE)
    assert detail is not None
    assert detail.title == 'Girl In The Mirror'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'Femjoy'
    assert detail.collections == ['Femjoy']
    assert detail.release_date == '2021-03-12'
    assert detail.genres == ['Threesome']
    assert [a.name for a in detail.actors] == ['Maria Rya', 'Bella', 'Cara']
    assert detail.actors[1].photo_url == 'https://cdn.fj.com/bella-real.jpg'
    assert detail.directors is not None
    assert detail.directors[0].name == 'Dir One'
    assert detail.art == ['https://cdn.fj.com/poster.jpg']
