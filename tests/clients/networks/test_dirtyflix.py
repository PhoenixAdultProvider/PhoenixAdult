from __future__ import annotations

import httpx
import respx

from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.networks.dirtyflix import DirtyFlixClient, __testing__
from phoenixadult.registry import find_site

SITE = find_site('Tricky Agent')
assert SITE is not None

_LISTING = """<div class="movie-block">
  <img src="/img/poster.jpg" />
  <ul><li><img src="https://trickyagent.com/tour_thumbs/tag001/1.jpg" /></li></ul>
  <h3>Cool Scene</h3>
  <div class="text">A summary.</div>
</div>"""

_TOUR = """<div class="thumbs-item"><img src="x/tour_thumbs/tag001/1.jpg" /><span class="added">2021-03-04</span></div>"""


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '%20'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


@respx.mock
async def test_search_and_detail_roundtrip() -> None:
    respx.get('https://dirtyflix.com/index.php/main/show_one_tour/11').mock(return_value=httpx.Response(200, text=_TOUR))
    respx.get('https://dirtyflix.com/index.php/main/show_one_tour/11/2').mock(return_value=httpx.Response(200, text='<html></html>'))
    respx.get('https://trickyagent.com/detailedTrailer/').mock(return_value=httpx.Response(200, text=_LISTING))

    results: list[SearchResult] = []
    await DirtyFlixClient().search(results, _ctx(search_date='2021-03-04'))
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].release_date == '2021-03-04'
    assert results[0].score == 100

    detail = await DirtyFlixClient().fetch_scene_detail(DirtyFlixClient().decode(results[0].cur_id), SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'Dirty Flix'
    assert detail.tagline == 'Tricky Agent'
    assert detail.collections == ['Tricky Agent']
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Agent', 'Casting']
    assert detail.art == ['https://trickyagent.com/img/poster.jpg']


def test_scene_actor_db() -> None:
    assert __testing__['scenes_for_actor_name']('Aggie') == ['wrygf726', 'wtag728']
    assert __testing__['scenes_for_actor_name']('aggie') == ['wrygf726', 'wtag728']
    assert 'Aggie' in __testing__['actors_for_scene_id']('wtag728')
    assert __testing__['scenes_for_actor_name']('Nobody') == []
