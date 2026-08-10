from __future__ import annotations

import json

from phoenixadult.registry import find_site
from phoenixadult.utils.helpers.helpers import b64url_encode, embed_subsite, pack_cur_id
from phoenixadult.utils.processors.scene_link import resolve_source_link


def test_a_url_and_date_payload_is_a_scene_link() -> None:
    link = resolve_source_link(pack_cur_id(['https://example.com/scene/alpha', '2024-01-01']), None)
    assert (link.kind, link.url) == ('scene', 'https://example.com/scene/alpha')
    assert resolve_source_link(pack_cur_id(['https://example.com/scene/alpha']), None).kind == 'scene'


def test_api_endpoints_are_classified_for_the_panel_not_the_link() -> None:
    assert resolve_source_link(pack_cur_id(['https://api.metadataapi.net/scenes/x']), None).kind == 'api'
    assert resolve_source_link(pack_cur_id(['https://site-api.project1service.com/v2/releases?type=scene&id=1']), None).kind == 'api'
    assert resolve_source_link(pack_cur_id(['https://www.sexart.com/api/movie?name=x&date=y']), None).kind == 'api'
    assert resolve_source_link(pack_cur_id(['https://www.example.com/graphql']), None).kind == 'api'


def test_a_url_in_a_later_segment_is_a_listing_link() -> None:
    dirtyflix = resolve_source_link(pack_cur_id(['someslug', '2019-04-12', 'https://sheisnerdy.com/detailed/3']), None)
    assert (dirtyflix.kind, dirtyflix.url) == ('listing', 'https://sheisnerdy.com/detailed/3')
    reptyle = resolve_source_link(pack_cur_id(['1234', 'scenes', 'https://example.com/videos?movie=1234']), None)
    assert (reptyle.kind, reptyle.url) == ('listing', 'https://example.com/videos?movie=1234')


def test_a_json_blob_with_a_url_key_links_and_carries_the_payload() -> None:
    blob = {'movieURL': 'https://www.adultempire.com/12345/movie.html', 'sceneNum': 2}
    link = resolve_source_link(b64url_encode(json.dumps(blob)), None)
    assert (link.kind, link.url) == ('scene', 'https://www.adultempire.com/12345/movie.html')
    assert link.payload == blob


def test_a_json_blob_without_a_url_is_panel_only() -> None:
    blob = {'title': 'A Scene', 'summary': 'words', 'poster': '/img/x.jpg'}
    link = resolve_source_link(b64url_encode(json.dumps(blob)), None)
    assert (link.kind, link.url) == ('json', None)
    assert link.payload == blob


def test_modelcentro_blobs_fill_the_id_template() -> None:
    site = find_site('Romi Rain')
    assert site is not None and site.direct_url_template == '{base}/scene/{id}/'
    link = resolve_source_link(b64url_encode(json.dumps({'id': 9, 'title': 'X'})), site)
    assert (link.kind, link.url) == ('scene', 'https://www.romirain.com/scene/9/')


def test_slug_sites_fill_the_head_template() -> None:
    cases = (
        ('Vixen', pack_cur_id(['a-scene-slug']), 'https://www.vixen.com/videos/a-scene-slug'),
        ('Nubiles Porn', pack_cur_id(['12345', '2024-01-01']), 'https://nubiles-porn.com/video/watch/12345'),
        ('Fast Times', pack_cur_id(['scene/foo-12345']), 'https://www.naughtyamerica.com/scene/foo-12345'),
        ('Swallowed', pack_cur_id(['deep-slug', '2024-01-01']), 'https://tour.swallowed.com/scenes/deep-slug'),
    )
    for name, cur_id, expected in cases:
        site = find_site(name)
        assert site is not None, name
        link = resolve_source_link(cur_id, site)
        assert (link.kind, link.url) == ('scene', expected), name


def test_a_slug_without_a_template_yields_nothing() -> None:
    site = find_site('Fit18')
    assert resolve_source_link(pack_cur_id(['bare-slug', '2024-01-01']), site).kind is None


def test_garbage_and_empty_ids_yield_nothing() -> None:
    assert resolve_source_link('cur1', None).kind is None
    assert resolve_source_link('', None).kind is None
    assert resolve_source_link('ÿþ', None).kind is None


def test_the_subsite_suffix_is_stripped_before_parsing() -> None:
    cur_id = embed_subsite(pack_cur_id(['https://example.com/scene/alpha', '2024-01-01']), 'Sub Site')
    link = resolve_source_link(cur_id, None)
    assert (link.kind, link.url) == ('scene', 'https://example.com/scene/alpha')
