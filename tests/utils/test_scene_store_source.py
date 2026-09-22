from __future__ import annotations

from typing import Any

from phoenixadult.utils.cache import layout as cache_layout
from phoenixadult.utils.cache import scene_store


def _payload(md_extra: dict[str, Any]) -> dict[str, Any]:
    md = {'type': 'movie', 'ratingKey': 'rk', 'guid': 'g', 'title': 'A Scene', 'studio': 'Studio', **md_extra}
    return {'MediaContainer': {'identifier': 'i', 'size': 1, 'Metadata': [md]}}


def _roundtrip(md_extra: dict[str, Any]) -> dict[str, Any]:
    scene_hash = cache_layout._hash('Studio', 'cur-src')
    scene_store.upsert('Studio', 'cur-src', scene_hash, cache_layout.bundle_path(scene_hash), _payload(md_extra))
    loaded = scene_store.load(scene_hash)
    assert loaded is not None
    return dict(loaded['MediaContainer']['Metadata'][0])


def test_the_source_reference_survives_the_store_round_trip() -> None:
    source = {'url': 'https://example.com/api/releases/alpha', 'kind': 'api', 'data': {'id': 9, 'nested': ['a', 'b']}}
    assert _roundtrip({'sourceRef': source})['sourceRef'] == source


def test_a_page_source_without_json_round_trips() -> None:
    source = {'url': 'https://example.com/scene/alpha', 'kind': 'page'}
    assert _roundtrip({'sourceRef': source})['sourceRef'] == source


def test_scenes_without_a_source_emit_none() -> None:
    assert 'sourceRef' not in _roundtrip({})


def test_a_rescrape_replaces_the_stored_source() -> None:
    _roundtrip({'sourceRef': {'url': 'https://example.com/old', 'kind': 'page', 'data': {'v': 1}}})
    md = _roundtrip({'sourceRef': {'url': 'https://example.com/new', 'kind': 'page'}})
    assert md['sourceRef'] == {'url': 'https://example.com/new', 'kind': 'page'}
