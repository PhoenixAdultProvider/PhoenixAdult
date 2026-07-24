from __future__ import annotations

from datetime import datetime

import httpx
import pytest
import respx

from phoenixadult.clients.aggregators.data18 import Data18Client, data18_ref, manual_mapping_url, mapping_slug, scene_url_from_ref

_SEARCH = (
    '<html>pages: 1'
    '<a href="/scenes/123-some-title">'
    '<p class="gen12 bold">Some Title</p>'
    '<span class="gen11"><b>#1</b> 2024-01-02 <i>BangBros</i></span>'
    '</a></html>'
)


async def test_manual_mapping_shortcut() -> None:
    url = await Data18Client().find_scene_url('thats-better-than-stealing-it-herfreshmanyear', 'whatever', [], None)
    assert url == 'https://www.data18.com/scenes/169646'


def test_mapping_slug_matches_the_client_formula() -> None:
    assert mapping_slug('Delicious Firsts', 'Hussie Pass') == 'delicious-firsts-hussiepass'
    assert mapping_slug('Solo Scene', None) == 'solo-scene'
    assert mapping_slug('', 'Whatever') is None


def test_mapping_slug_strips_apostrophes_to_match_mapping_values() -> None:
    assert mapping_slug("That's Better Than Stealing It", 'Her Freshman Year') == 'thats-better-than-stealing-it-herfreshmanyear'
    assert manual_mapping_url(mapping_slug("That's Better Than Stealing It", 'Her Freshman Year')) == 'https://www.data18.com/scenes/169646'


def test_manual_mapping_url_resolves_value_to_key() -> None:
    assert manual_mapping_url('delicious-firsts-hussiepass') == 'https://www.data18.com/scenes/1313219'
    assert manual_mapping_url('not-a-mapped-slug') is None
    assert manual_mapping_url(None) is None


def test_data18_ref_extracts_type_and_id() -> None:
    assert data18_ref('https://www.data18.com/scenes/1125441') == {'type': 'scene', 'id': '1125441'}
    assert data18_ref('https://www.data18.com/movies/1133091-smilf') == {'type': 'movie', 'id': '1133091'}
    assert data18_ref('https://www.data18.com/name/somebody') is None
    assert data18_ref('') is None
    assert data18_ref(None) is None


@respx.mock
async def test_find_scene_url_scores_match() -> None:
    respx.route(method='GET', url__regex=r'data18\.com/sys/live\.php').mock(return_value=httpx.Response(200, text=_SEARCH))
    url = await Data18Client().find_scene_url(None, 'Some Title', ['BangBros'], datetime(2024, 1, 2))
    assert url == 'https://www.data18.com/scenes/123-some-title'


@respx.mock
async def test_find_scene_url_movie_kind_matches_movie_hrefs() -> None:
    movie_search = _SEARCH.replace('/scenes/123-some-title', '/movies/123-some-title')
    respx.route(method='GET', url__regex=r'data18\.com/sys/live\.php').mock(return_value=httpx.Response(200, text=movie_search))
    client = Data18Client()
    assert await client.find_scene_url(None, 'Some Title', ['BangBros'], datetime(2024, 1, 2), kind='movie') == 'https://www.data18.com/movies/123-some-title'
    assert await client.find_scene_url(None, 'Some Title', ['BangBros'], datetime(2024, 1, 2)) is None


@respx.mock
async def test_find_scene_url_rejects_low_accuracy() -> None:
    respx.route(method='GET', url__regex=r'data18\.com/sys/live\.php').mock(return_value=httpx.Response(200, text=_SEARCH))
    url = await Data18Client().find_scene_url(None, 'Totally Different', ['OtherStudio'], datetime(2010, 5, 5))
    assert url is None


@respx.mock
async def test_find_scene_url_retries_with_digit_title() -> None:
    digit_search = _SEARCH.replace('Some Title', 'World War XXX: Part 2').replace('/scenes/123-some-title', '/scenes/456-ww-xxx-part-2')
    respx.route(method='GET', url__regex=r'data18\.com/sys/live\.php').mock(return_value=httpx.Response(200, text=digit_search))
    url = await Data18Client().find_scene_url(None, 'World War XXX: Part Two', ['BangBros'], datetime(2024, 1, 2))
    assert url == 'https://www.data18.com/scenes/456-ww-xxx-part-2'


@respx.mock
async def test_fetch_images_retries_id_url_via_manual_redirect_hop() -> None:
    scene = '<html><div id="galleriesoff"></div><div id="moviewrap"><img src="https://cdn.example/poster.jpg"></div></html>'
    slug_url = 'https://www.data18.com/scenes/1209198-vr-captain-marvel-parody'
    respx.get('https://www.data18.com/scenes/1209198').mock(side_effect=[httpx.Response(403), httpx.Response(301, headers={'location': slug_url})])
    respx.get(slug_url).mock(return_value=httpx.Response(200, text=scene))
    imgs = await Data18Client().fetch_images('https://www.data18.com/scenes/1209198')
    assert imgs == ['https://cdn.example/poster.jpg']


@respx.mock
async def test_fetch_images_refuses_off_host_redirect() -> None:
    respx.get('https://www.data18.com/scenes/1209198').mock(side_effect=[httpx.Response(403), httpx.Response(301, headers={'location': 'https://evil.com/x'})])
    imgs = await Data18Client().fetch_images('https://www.data18.com/scenes/1209198')
    assert imgs == []


@respx.mock
async def test_fetch_images_poster_only() -> None:
    scene = '<html><div id="galleriesoff"></div><div id="moviewrap"><img src="https://cdn.example/poster.jpg"></div></html>'
    respx.route(method='GET', url__regex=r'data18\.com/scenes/').mock(return_value=httpx.Response(200, text=scene))
    imgs = await Data18Client().fetch_images('https://www.data18.com/scenes/123-x')
    assert imgs == ['https://cdn.example/poster.jpg']


@respx.mock
async def test_fetch_images_includes_related_scene_cover() -> None:
    scene = (
        '<html><div id="galleriesoff"></div>'
        '<div id="moviewrap"><img src="https://cdn.example/poster.jpg"></div>'
        '<a href="https://cdn.dt18.com/full_covers/8/1227431-front-dvd.jpg" data-lightbox="relatedscenecover">x</a>'
        '</html>'
    )
    respx.route(method='GET', url__regex=r'data18\.com/scenes/').mock(return_value=httpx.Response(200, text=scene))
    imgs = await Data18Client().fetch_images('https://www.data18.com/scenes/123-x')
    assert imgs == ['https://cdn.example/poster.jpg', 'https://cdn.dt18.com/full_covers/8/1227431-front-dvd.jpg']


def test_scene_url_from_ref_accepts_id_slug_and_url() -> None:
    url = 'https://www.data18.com/scenes/1150700'
    assert scene_url_from_ref('1150700') == url
    assert scene_url_from_ref('  1150700  ') == url
    assert scene_url_from_ref('scenes/1150700') == url
    assert scene_url_from_ref('/scenes/1150700/') == url
    assert scene_url_from_ref(url) == url
    assert scene_url_from_ref('http://data18.com/scenes/1150700') == url
    assert scene_url_from_ref('delicious-firsts-hussiepass') == 'https://www.data18.com/scenes/delicious-firsts-hussiepass'


def test_scene_url_from_ref_accepts_movie_refs() -> None:
    url = 'https://www.data18.com/movies/1227431'
    assert scene_url_from_ref('movies/1227431') == url
    assert scene_url_from_ref('/movies/1227431/') == url
    assert scene_url_from_ref(url) == url
    assert scene_url_from_ref('http://data18.com/movies/1227431') == url


def test_scene_url_from_ref_refuses_off_host_and_junk() -> None:
    for bad in (
        None,
        '',
        '/',
        'scenes',
        'scenes/',
        'movies',
        'movies/',
        'https://evil.com/scenes/1150700',
        'https://www.data18.com.evil.com/scenes/1',
        'https://evil.com/movies/1227431',
        '../../etc/passwd',
        'scenes/a b',
        '1150700?x=1',
    ):
        assert scene_url_from_ref(bad) is None, bad


def test_manual_mapping_list_values_resolve_to_the_shared_scene() -> None:
    assert manual_mapping_url('valentines-day-affair-best-moments-brazzerslive') == 'https://www.data18.com/scenes/1233354'
    assert manual_mapping_url('valentines-day-affair-unseen-moments-brazzerslive') == 'https://www.data18.com/scenes/1233354'


def test_manual_mapping_movie_type_builds_movie_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.clients.aggregators.data18 import DATA18_MANUAL_MAPPINGS

    monkeypatch.setitem(DATA18_MANUAL_MAPPINGS, '1227431', {'slug': '2-broke-girls-a-xxx-parody-somesite', 'type': 'movie'})
    assert manual_mapping_url('2-broke-girls-a-xxx-parody-somesite') == 'https://www.data18.com/movies/1227431'


async def test_enrich_images_allow_square_false_drops_squares(monkeypatch: pytest.MonkeyPatch) -> None:
    import phoenixadult.clients.aggregators.data18 as data18_module

    client = Data18Client()
    urls = ['https://cdn.example/sq.jpg', 'https://cdn.example/wide.jpg', 'https://cdn.example/unprobed.jpg']

    async def fake_fetch(scene_url: str) -> list[str]:
        return urls

    async def fake_dims(url: str, referers: object = None, cookies: object = None) -> dict[str, int] | None:
        return {'sq': {'width': 800, 'height': 800}, 'wide': {'width': 1920, 'height': 1080}}.get(url.rsplit('/', 1)[-1].split('.')[0])

    monkeypatch.setattr(client, 'fetch_images', fake_fetch)
    monkeypatch.setattr(data18_module, 'fetch_dimensions', fake_dims)

    images: list[str] = []
    await client.enrich_images(scope='x', images=images, forced_url='https://www.data18.com/scenes/1150700', allow_square=False)
    assert images == ['https://cdn.example/wide.jpg', 'https://cdn.example/unprobed.jpg']

    images = []
    await client.enrich_images(scope='x', images=images, forced_url='https://www.data18.com/scenes/1150700')
    assert images == urls


async def test_enrich_images_routes_by_resolved_url_type(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Data18Client()
    calls: list[str] = []

    async def fake_scene(url: str) -> list[str]:
        calls.append(f'scene:{url}')
        return ['https://cdn.example/s.jpg']

    async def fake_movie(url: str, page_sel: object = None) -> list[str]:
        calls.append(f'movie:{url}')
        return ['https://cdn.example/m.jpg']

    monkeypatch.setattr(client, 'fetch_images', fake_scene)
    monkeypatch.setattr(client, 'fetch_movie_images', fake_movie)

    images: list[str] = []
    await client.enrich_images(scope='x', images=images, forced_url='https://www.data18.com/movies/1227431')
    await client.enrich_images(scope='x', images=images, forced_url='https://www.data18.com/scenes/1150700')
    assert calls == ['movie:https://www.data18.com/movies/1227431', 'scene:https://www.data18.com/scenes/1150700']
    assert images == ['https://cdn.example/m.jpg', 'https://cdn.example/s.jpg']


def test_manual_mappings_have_no_duplicate_keys() -> None:
    import collections
    import json
    import pathlib

    dupes: list[str] = []
    owner: dict[str, str] = {}

    def hook(pairs: list[tuple[str, object]]) -> dict[str, object]:
        keys = collections.Counter(k for k, _ in pairs)
        dupes.extend(k for k, n in keys.items() if n > 1)
        return dict(pairs)

    for f in sorted(pathlib.Path('phoenixadult/clients/aggregators/_data/data18').glob('data18_manual_mappings*.json')):
        data = json.loads(f.read_text(encoding='utf-8'), object_pairs_hook=hook)
        for k in data:
            if k in owner:
                dupes.append(f'{k} ({owner[k]} vs {f.name})')
            owner[k] = f.name

    assert not dupes, f'duplicate mapping keys silently shadow earlier entries: {dupes}'


def test_manual_mappings_entries_are_well_formed() -> None:
    from phoenixadult.clients.aggregators.data18 import DATA18_MANUAL_MAPPINGS

    for d18, entry in DATA18_MANUAL_MAPPINGS.items():
        assert d18.isdigit(), d18
        assert entry['type'] in ('scene', 'movie'), d18
        slug = entry['slug']
        assert slug and (isinstance(slug, str) or (isinstance(slug, list) and all(s for s in slug))), d18


def test_manual_mappings_merge_sibling_files(tmp_path: pytest.TempPathFactory) -> None:
    import json
    from pathlib import Path

    from phoenixadult.clients.aggregators.data18 import _load_manual_mappings

    folder = Path(str(tmp_path)) / '_data' / 'data18'
    folder.mkdir(parents=True)
    (folder / 'data18_manual_mappings.json').write_text(
        json.dumps({'1': {'slug': 'base-scene', 'type': 'scene'}, '2': {'slug': 'overridden', 'type': 'scene'}}), encoding='utf-8'
    )
    (folder / 'data18_manual_mappings_brazzers.json').write_text(json.dumps({'2': {'slug': 'brazzers-wins', 'type': 'movie'}}), encoding='utf-8')
    (folder / 'data18_manual_mappings_vrcosplayx.json').write_text(json.dumps({'3': {'slug': 'cosplay-scene', 'type': 'scene'}}), encoding='utf-8')
    (folder / 'unrelated.json').write_text(json.dumps({'9': {'slug': 'ignored', 'type': 'scene'}}), encoding='utf-8')

    merged = _load_manual_mappings(str(Path(str(tmp_path)) / 'fake_module.py'))
    assert merged == {
        '1': {'slug': 'base-scene', 'type': 'scene'},
        '2': {'slug': 'brazzers-wins', 'type': 'movie'},
        '3': {'slug': 'cosplay-scene', 'type': 'scene'},
    }
