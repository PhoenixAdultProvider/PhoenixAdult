from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from phoenixadult.utils.cache import BUNDLE_FILE, bundle_path, bundle_sweep, scene_store


def _write_bundle(root: Path, scene_hash: str, site: str = 'Fit18', title: str = 'Recovered Scene', version: int = 1) -> Path:
    payload: dict[str, Any] = {
        'version': version,
        'site': site,
        'cur_id': f'cur-{scene_hash}',
        'hash': scene_hash,
        'images': {f'/cache/{bundle_path(scene_hash)}/images/img-02.jpg': [1280, 720, 12345]},
        'response': {
            'MediaContainer': {
                'identifier': 'tv.plex.agents.custom.phoenixadult',
                'size': 1,
                'Metadata': [{'type': 'movie', 'ratingKey': f'scene-fit18-cur-{scene_hash}', 'title': title, 'studio': site}],
            }
        },
    }
    bundle = root / bundle_path(scene_hash)
    bundle.mkdir(parents=True)
    path = bundle / BUNDLE_FILE
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path


def test_sweep_adopts_bundles_the_store_does_not_know(tmp_path: Path) -> None:
    _write_bundle(tmp_path, 'aaaaaaaaaaaa')
    _write_bundle(tmp_path, 'bbbbbbbbbbbb', title='Second Recovered Scene')

    stats = bundle_sweep.sweep(tmp_path)

    assert stats == {'adopted': 2, 'skipped': 0, 'unreadable': 0}
    assert scene_store.has('aaaaaaaaaaaa') and scene_store.has('bbbbbbbbbbbb')
    titles = {row['title'] for row in scene_store.site_scenes('Fit18')}
    assert titles == {'Recovered Scene', 'Second Recovered Scene'}


def test_sweep_skips_known_bundles_without_touching_them(tmp_path: Path) -> None:
    path = _write_bundle(tmp_path, 'aaaaaaaaaaaa')
    bundle_sweep.sweep(tmp_path)

    payload = json.loads(path.read_text(encoding='utf-8'))
    payload['response']['MediaContainer']['Metadata'][0]['title'] = 'Edited on Disk'
    path.write_text(json.dumps(payload), encoding='utf-8')

    assert bundle_sweep.sweep(tmp_path) == {'adopted': 0, 'skipped': 1, 'unreadable': 0}
    assert scene_store.site_scenes('Fit18')[0]['title'] == 'Recovered Scene'

    assert bundle_sweep.sweep(tmp_path, overwrite=True) == {'adopted': 1, 'skipped': 0, 'unreadable': 0}
    assert scene_store.site_scenes('Fit18')[0]['title'] == 'Edited on Disk'


def test_sweep_counts_unreadable_bundles(tmp_path: Path) -> None:
    path = _write_bundle(tmp_path, 'aaaaaaaaaaaa')
    path.write_text('{broken', encoding='utf-8')
    _write_bundle(tmp_path, 'cccccccccccc', version=99)

    assert bundle_sweep.sweep(tmp_path) == {'adopted': 0, 'skipped': 0, 'unreadable': 2}
    assert not scene_store.has('aaaaaaaaaaaa')


def test_startup_sweep_registers_copied_in_bundles(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cache = tmp_path / 'sweep-cache'
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(cache))
    _write_bundle(cache, 'dddddddddddd')

    bundle_sweep.startup_sweep()

    assert scene_store.has('dddddddddddd')


def test_startup_sweep_noops_when_the_cache_is_off(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cache = tmp_path / 'sweep-cache'
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'false')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(cache))
    _write_bundle(cache, 'eeeeeeeeeeee')

    bundle_sweep.startup_sweep()

    assert not scene_store.has('eeeeeeeeeeee')
