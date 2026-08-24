from __future__ import annotations

import json

import httpx
import pytest
import respx

import phoenixadult.clients.aggregators.data18 as data18_module
from phoenixadult.clients.base import SearchContext, SearchResult
from phoenixadult.clients.networks.reptyle import ReptyleClient
from phoenixadult.registry import find_site

SITE = find_site('TeamSkeet')
assert SITE is not None


def _ctx(title: str = 'cool scene', **kw: object) -> SearchContext:
    return SearchContext(title=title, encoded=title.replace(' ', '+'), search_site=SITE.name, site_info=SITE, **kw)  # type: ignore[arg-type]


def _state_html(content: dict) -> str:
    return f'<html><script>window.__INITIAL_STATE__ = {json.dumps({"content": content})};</script></html>'


_SCENE = {
    'title': 'Cool Scene',
    'description': '<p>A summary</p>',
    'img': 'https://cdn/p.jpg',
    'site': {'name': 'Family Strokes'},
    'publishedDate': '2021-03-04T00:00:00Z',
    'models': [{'modelId': 'm1', 'modelName': 'Jane Doe'}, {'modelId': 'm2', 'modelName': 'John Smith'}],
    'tags': ['Taboo'],
    'id': 'cool-scene',
}


@respx.mock
async def test_search() -> None:
    url = 'https://www.teamskeet.com/movies/cool-scene'
    respx.get(url).mock(return_value=httpx.Response(200, text=_state_html({'moviesContent': {'cool-scene': _SCENE}})))
    respx.get(url__regex=r'.*/models/.*').mock(return_value=httpx.Response(200, text=_state_html({'modelsContent': {}})))
    results: list[SearchResult] = []
    await ReptyleClient().search(results, _ctx())
    assert len(results) == 1
    assert results[0].title == 'Cool Scene'
    assert results[0].thumb_url == 'https://cdn/p.jpg'
    assert results[0].subsite == 'Family Strokes'
    assert ReptyleClient().decode(results[0].cur_id) == f'cool-scene|moviesContent|{url}'


@respx.mock
async def test_detail() -> None:
    url = 'https://www.teamskeet.com/movies/cool-scene'
    respx.get(url).mock(return_value=httpx.Response(200, text=_state_html({'moviesContent': {'cool-scene': _SCENE}})))
    respx.get('https://www.teamskeet.com/models/m1').mock(
        return_value=httpx.Response(200, text=_state_html({'modelsContent': {'m1': {'img': 'https://cdn/jane.jpg', 'gender': 'female'}}}))
    )
    respx.get('https://www.teamskeet.com/models/m2').mock(
        return_value=httpx.Response(200, text=_state_html({'modelsContent': {'m2': {'img': 'https://cdn/john.jpg', 'gender': 'male'}}}))
    )
    detail = await ReptyleClient().fetch_scene_detail(f'cool-scene|moviesContent|{url}', SITE)
    assert detail is not None
    assert detail.title == 'Cool Scene'
    assert detail.summary == 'A summary.'
    assert detail.studio == 'TeamSkeet'
    assert detail.tagline == 'Family Strokes'
    assert detail.collections == ['Family Strokes']
    assert detail.release_date == '2021-03-04'
    assert detail.genres == ['Taboo', 'Threesome']
    assert detail.actors[0].name == 'Jane Doe'
    assert detail.actors[0].photo_url == 'https://cdn/jane.jpg'
    assert detail.actors[0].gender == 'female'
    assert detail.art == ['https://cdn/p.jpg']


@respx.mock
async def test_detail_data18_enrichment_keys_off_the_slug_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('DATA18_ENABLE', 'true')
    url = 'https://www.teamskeet.com/movies/cool-scene'
    respx.get(url).mock(return_value=httpx.Response(200, text=_state_html({'moviesContent': {'cool-scene': _SCENE}})))
    respx.get('https://www.teamskeet.com/models/m1').mock(
        return_value=httpx.Response(200, text=_state_html({'modelsContent': {'m1': {'img': 'https://cdn/jane.jpg', 'gender': 'female'}}}))
    )
    respx.get('https://www.teamskeet.com/models/m2').mock(
        return_value=httpx.Response(200, text=_state_html({'modelsContent': {'m2': {'img': 'https://cdn/john.jpg', 'gender': 'male'}}}))
    )
    captured: dict[str, object] = {}

    class FakeData18(data18_module.Data18Client):
        async def find_scene_url(
            self,
            scene_id: str | None,
            query: str,
            providers: list[str],
            scene_date: object,
            kind: str = 'scene',
            search: bool = True,
            actors: list[str] | None = None,
        ) -> str:
            captured['mapping_id'] = scene_id
            return 'https://www.data18.com/scenes/999'

        async def fetch_images(self, scene_url: str) -> list[str]:
            return ['https://cdn.data18.com/extra.jpg']

    monkeypatch.setattr(data18_module, 'Data18Client', FakeData18)
    detail = await ReptyleClient().fetch_scene_detail(f'cool-scene|moviesContent|{url}', SITE)
    assert detail is not None
    assert captured['mapping_id'] == 'cool-scene-familystrokes'
    assert 'https://cdn.data18.com/extra.jpg' in detail.art


def test_data18_disable_list_matches_exact_names_and_wildcards() -> None:
    from phoenixadult.clients.networks.reptyle import _data18_search_disabled

    assert _data18_search_disabled('Rub a Teen')
    assert _data18_search_disabled('Rub A Teen')
    assert _data18_search_disabled('Lust HD')
    assert _data18_search_disabled('MYLF X Series')
    assert _data18_search_disabled('TeamSkeet X Eva Elfie')
    assert _data18_search_disabled('MYLF X Dante Colle')
    assert not _data18_search_disabled('Family Strokes')
    assert not _data18_search_disabled('Shoplyfter')


@respx.mock
async def test_data18_search_is_disabled_for_listed_sub_sites_but_mappings_still_force(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('DATA18_ENABLE', 'true')
    url = 'https://www.teamskeet.com/movies/cool-scene'
    scene = dict(_SCENE, site={'name': 'Rub A Teen'}, models=[])
    respx.get(url).mock(return_value=httpx.Response(200, text=_state_html({'moviesContent': {'cool-scene': scene}})))
    captured: dict[str, object] = {}

    class FakeData18(data18_module.Data18Client):
        async def find_scene_url(
            self,
            scene_id: str | None,
            query: str,
            providers: list[str],
            scene_date: object,
            kind: str = 'scene',
            search: bool = True,
            actors: list[str] | None = None,
        ) -> str | None:
            captured['search'] = search
            captured['scene_id'] = scene_id
            return data18_module.manual_mapping_url(scene_id) if not search else 'https://www.data18.com/scenes/999'

    monkeypatch.setattr(data18_module, 'Data18Client', FakeData18)
    detail = await ReptyleClient().fetch_scene_detail(f'cool-scene|moviesContent|{url}', SITE)
    assert detail is not None
    assert captured['search'] is False
    assert captured['scene_id'] == 'cool-scene-rubateen'
    assert detail.data18_url is None


@respx.mock
async def test_a_leading_episode_tag_is_dropped_from_search_and_detail() -> None:
    url = 'https://www.teamskeet.com/movies/cool-scene'
    tagged = {**_SCENE, 'title': 'S1E3: Sneaky, Bratty Lil Stepsis', 'models': []}
    respx.get(url).mock(return_value=httpx.Response(200, text=_state_html({'moviesContent': {'cool-scene': tagged}})))
    respx.get(url__regex=r'.*/models/.*').mock(return_value=httpx.Response(200, text=_state_html({'modelsContent': {}})))

    results: list[SearchResult] = []
    await ReptyleClient().search(results, _ctx())
    assert [r.title for r in results] == ['Sneaky, Bratty Lil Stepsis']

    detail = await ReptyleClient().fetch_scene_detail(f'cool-scene|moviesContent|{url}', SITE)
    assert detail is not None
    assert detail.title == 'Sneaky, Bratty Lil Stepsis'


@respx.mock
async def test_data18_slug_keeps_the_site_when_it_is_also_the_sub_site(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('DATA18_ENABLE', 'true')
    site = find_site('Family Strokes')
    assert site is not None

    url = 'https://www.familystrokes.com/movies/cool-scene'
    respx.get(url).mock(return_value=httpx.Response(200, text=_state_html({'moviesContent': {'cool-scene': _SCENE}})))
    respx.get(url__regex=r'.*/models/.*').mock(return_value=httpx.Response(200, text=_state_html({'modelsContent': {}})))
    captured: dict[str, object] = {}

    class FakeData18(data18_module.Data18Client):
        async def find_scene_url(
            self,
            scene_id: str | None,
            query: str,
            providers: list[str],
            scene_date: object,
            kind: str = 'scene',
            search: bool = True,
            actors: list[str] | None = None,
        ) -> str | None:
            captured['mapping_id'] = scene_id
            return None

    monkeypatch.setattr(data18_module, 'Data18Client', FakeData18)
    detail = await ReptyleClient().fetch_scene_detail(f'cool-scene|moviesContent|{url}', site)

    assert detail is not None
    assert captured['mapping_id'] == 'cool-scene-familystrokes'


def test_model_name_candidates_split_like_the_filename_examples() -> None:
    from phoenixadult.clients.networks.reptyle import _model_name_candidates

    assert _model_name_candidates('Gia Ohmy') == ['Gia Ohmy']
    assert _model_name_candidates('Gia Ohmy And Lolly Dames') == ['Gia Ohmy', 'Lolly Dames']
    assert _model_name_candidates('Brina Scarlet Fun Sized Megan And Lilibet Saunders') == [
        'Brina Scarlet',
        'Fun Sized Megan',
        'Brina Scarlet Fun',
        'Sized Megan',
        'Brina Scarlet Fun Sized',
        'Megan',
        'Lilibet Saunders',
    ]


_MOVIE = {
    'id': 'cool-scene',
    'title': 'Cool Scene',
    'img': 'https://cdn/p.jpg',
    'type': 'video',
    'site': {'name': 'Family Strokes'},
    'publishedDate': '2021-03-04T00:00:00',
}
_EMPTY_STATE = {'modelsContent': {}, 'videosContent': {}, 'seriesContent': {}}


@respx.mock
async def test_the_direct_hit_is_not_duplicated_when_the_model_page_lists_the_same_scene() -> None:
    hit_url = 'https://www.teamskeet.com/movies/gia-ohmy'
    scene = dict(_SCENE, id='cool-scene', type='video')
    respx.get(hit_url).mock(return_value=httpx.Response(200, text=_state_html({'videosContent': {'gia-ohmy': scene}})))
    model = {'name': 'Gia OhMy', 'movies': [_MOVIE]}
    respx.get('https://www.teamskeet.com/models/gia-ohmy').mock(return_value=httpx.Response(200, text=_state_html({'modelsContent': {'gia-ohmy': model}})))

    results: list[SearchResult] = []
    await ReptyleClient().search(results, _ctx('Gia Ohmy'))

    assert [r.title for r in results] == ['Cool Scene']
    assert ReptyleClient().decode(results[0].cur_id) == 'cool-scene|videosContent|https://www.teamskeet.com/movies/cool-scene'


@respx.mock
async def test_a_direct_hit_is_supplemented_with_the_model_page_movies() -> None:
    hit_url = 'https://www.teamskeet.com/movies/gia-ohmy'
    respx.get(hit_url).mock(return_value=httpx.Response(200, text=_state_html({'moviesContent': {'gia-ohmy': dict(_SCENE, id='gia-ohmy')}})))
    model = {'name': 'Gia OhMy', 'movies': [{'id': 'other-scene', 'title': 'Other Scene', 'type': 'movie', 'site': {'name': 'BFFS'}}]}
    respx.get('https://www.teamskeet.com/models/gia-ohmy').mock(return_value=httpx.Response(200, text=_state_html({'modelsContent': {'gia-ohmy': model}})))

    results: list[SearchResult] = []
    await ReptyleClient().search(results, _ctx('Gia Ohmy'))

    assert [r.title for r in results] == ['Other Scene', 'Cool Scene']
    assert ReptyleClient().decode(results[1].cur_id) == f'gia-ohmy|moviesContent|{hit_url}'


@respx.mock
async def test_search_falls_back_to_the_model_page_when_the_movie_slug_misses() -> None:
    respx.get('https://www.teamskeet.com/movies/gia-ohmy').mock(return_value=httpx.Response(200, text=_state_html(_EMPTY_STATE)))
    model = {'name': 'Gia OhMy', 'movies': [_MOVIE, {'id': 'other-scene', 'title': 'Other Scene', 'type': 'movie', 'site': {'name': 'BFFS'}}]}
    respx.get('https://www.teamskeet.com/models/gia-ohmy').mock(return_value=httpx.Response(200, text=_state_html({'modelsContent': {'gia-ohmy': model}})))

    results: list[SearchResult] = []
    await ReptyleClient().search(results, _ctx('Gia Ohmy'))

    assert [r.title for r in results] == ['Cool Scene', 'Other Scene']
    assert results[0].scene_url == 'https://www.teamskeet.com/movies/cool-scene'
    assert results[0].subsite == 'Family Strokes'
    assert ReptyleClient().decode(results[0].cur_id) == 'cool-scene|videosContent|https://www.teamskeet.com/movies/cool-scene'
    assert ReptyleClient().decode(results[1].cur_id) == 'other-scene|moviesContent|https://www.teamskeet.com/movies/other-scene'


@respx.mock
async def test_model_fallback_tries_split_names_and_survives_a_404_page() -> None:
    title = 'Brina Scarlet Fun Sized Megan And Lilibet Saunders'
    respx.get('https://www.teamskeet.com/movies/brina-scarlet-fun-sized-megan-and-lilibet-saunders').mock(
        return_value=httpx.Response(200, text=_state_html(_EMPTY_STATE))
    )
    respx.get('https://www.teamskeet.com/models/brina-scarlet').mock(return_value=httpx.Response(404, text=_state_html(_EMPTY_STATE)))
    model = {'name': 'Fun Sized Megan', 'movies': [_MOVIE]}
    respx.get('https://www.teamskeet.com/models/fun-sized-megan').mock(
        return_value=httpx.Response(200, text=_state_html({'modelsContent': {'fun-sized-megan': model}}))
    )

    results: list[SearchResult] = []
    await ReptyleClient().search(results, _ctx(title))

    assert [r.title for r in results] == ['Cool Scene']


@respx.mock
async def test_model_fallback_gives_up_when_no_candidate_matches() -> None:
    respx.get(url__regex=r'.*').mock(return_value=httpx.Response(200, text=_state_html(_EMPTY_STATE)))
    results: list[SearchResult] = []
    await ReptyleClient().search(results, _ctx('Gia Ohmy And Lolly Dames'))
    assert results == []


@respx.mock
async def test_search_canonicalizes_an_alias_slug() -> None:
    alias = 'chloe-rose-cool-scene'
    aliased = dict(_SCENE, id='cool-scene')
    respx.get(f'https://www.teamskeet.com/movies/{alias}').mock(return_value=httpx.Response(200, text=_state_html({'videosContent': {alias: aliased}})))
    respx.get(url__regex=r'.*/models/.*').mock(return_value=httpx.Response(200, text=_state_html({'modelsContent': {}})))

    results: list[SearchResult] = []
    await ReptyleClient().search(results, _ctx('Chloe Rose Cool Scene'))

    assert len(results) == 1
    composite = ReptyleClient().decode(results[0].cur_id)
    assert composite == 'cool-scene|videosContent|https://www.teamskeet.com/movies/cool-scene'
    assert results[0].scene_url == 'https://www.teamskeet.com/movies/cool-scene'
