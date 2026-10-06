from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from phoenixadult.utils.cache import layout as cache_layout
from tests.support import authed_client


def _snapshot_key() -> str:
    from phoenixadult.utils.cache import scene_store

    md = {'type': 'movie', 'ratingKey': 'rk', 'guid': 'g', 'title': 'Scene', 'studio': 'Studio'}
    scene_hash = cache_layout.scene_hash_for('Studio', 'cur1')
    payload = {'MediaContainer': {'identifier': 'i', 'size': 1, 'Metadata': [md]}}
    scene_store.upsert('Studio', 'cur1', scene_hash, cache_layout.bundle_path(scene_hash), payload)
    return str(scene_store.snapshot_state('Studio', 'cur1')['key'])


@pytest.fixture
def pages(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    monkeypatch.setenv('DEV_UI_ENABLE', 'true')
    rendered = {'setup': TestClient(create_app()).get('/setup').text}
    client = authed_client()
    key = _snapshot_key()
    paths = {
        'config': '/config',
        'metadata': '/metadata',
        'metadata-edit': f'/metadata/edit?key={key}',
        'people': '/people',
        'logos': '/logos',
        'queue': '/queue',
        'searches': '/searches',
        'account': '/account',
        'dev': '/dev',
    }
    rendered.update({name: client.get(path).text for name, path in paths.items()})
    rendered['login'] = TestClient(create_app()).get('/login').text
    assert 'id="setupForm"' in rendered['setup'], 'the setup page must be captured before an account exists'
    return rendered
