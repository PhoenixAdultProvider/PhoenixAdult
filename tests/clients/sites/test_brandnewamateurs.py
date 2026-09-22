from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.sites.brandnewamateurs import BrandNewAmateursClient
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site

SITE = find_site('Brand New Amateurs')
assert SITE is not None

MODEL_HTML = """<html><body>
  <div class="item-video">
    <div class="item-thumb"><a href="/scenes/first.html" title="First Scene">x</a></div>
  </div>
  <h3>Jane Doe</h3>
  <div class="profile-pic"><img src0_3x="https://cdn.bna.com/jane.jpg"></div>
</body></html>"""

DETAIL_HTML = """<html><head>
  <meta name="twitter:image" content="https://cdn.bna.com/poster.jpg">
</head><body>
  <h3>First Scene</h3>
  <div class="videoDetails clear"><p>A blurb.</p></div>
  <ul><li>Tags:</li><li><a>Amateur</a></li><li><a>POV</a></li></ul>
</body></html>"""


@respx.mock
async def test_search_lists_model_scenes() -> None:
    model_url = 'https://brandnewamateurs.com/models/JaneDoe.html'
    respx.get(model_url).mock(return_value=httpx.Response(200, text=MODEL_HTML))
    results: list[SearchResult] = []
    await BrandNewAmateursClient().search(results, SearchContext(title='Jane Doe', encoded='', search_site=SITE.name, site_info=SITE))
    assert len(results) == 1
    assert results[0].title == 'First Scene'
    assert results[0].scene_url == 'https://brandnewamateurs.com/scenes/first.html'


@respx.mock
async def test_detail_fields_genres_actor_via_packed_curid() -> None:
    import json

    from phoenixadult.utils.helpers.ids import pack_cur_id

    scene_url = 'https://brandnewamateurs.com/scenes/first.html'
    model_url = 'https://brandnewamateurs.com/models/JaneDoe.html'
    respx.get(scene_url).mock(return_value=httpx.Response(200, text=DETAIL_HTML))
    respx.get(model_url).mock(return_value=httpx.Response(200, text=MODEL_HTML))
    payload = json.dumps({'sceneURL': scene_url, 'actorURL': model_url, 'releaseDate': '2021-06-06'})
    cur_id = pack_cur_id([payload])
    detail = await BrandNewAmateursClient().fetch_scene_detail(BrandNewAmateursClient().decode(cur_id), SITE)
    assert detail is not None
    assert detail.title == 'First Scene'
    assert detail.summary == 'A blurb.'
    assert detail.studio == 'Brand New Amateurs'
    assert detail.collections == ['Brand New Amateurs']
    assert detail.release_date == '2021-06-06'
    assert detail.genres == ['Amateur', 'POV']
    assert len(detail.actors) == 1
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://cdn.bna.com/jane.jpg'
    assert detail.art == ['https://cdn.bna.com/poster.jpg']
