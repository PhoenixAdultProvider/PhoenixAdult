from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from phoenixadult.app_factory import create_app
from phoenixadult.models.metadata import PlexMetadataResponse
from phoenixadult.utils import cache as mc
from phoenixadult.utils.cache import scene_store
from phoenixadult.utils.images import image_fetcher

SITE = 'Brazzers'
CUR_ID = 'cur1'


def _snapshot(tmp_path: Path, **overrides: Any) -> str:
    md: dict[str, Any] = {
        'type': 'movie',
        'ratingKey': 'scene-brazzers-cur1',
        'guid': 'g',
        'title': 'A Cached Scene',
        'titleSort': 'Cached Scene, A',
        'studio': 'Brazzers',
        'tagline': 'Baby Got Boobs',
        'summary': 'Old summary.',
        'originallyAvailableAt': '2024-01-02',
        'Genre': [{'tag': 'Anal'}],
        'Collection': [{'tag': 'Baby Got Boobs'}],
        'Role': [{'tag': 'Jane Doe', 'thumb': 'http://host/images/local/actor/jane-doe.jpg'}],
        'Director': [{'tag': 'Some Director'}],
        'Image': [{'url': '/cache/brazzers/x/images/poster-00.jpg', 'type': 'coverPoster'}],
        **overrides,
    }
    data = {'MediaContainer': {'identifier': 'phoenixadult', 'size': 1, 'Metadata': [md]}}
    rel = f'brazzers/{mc._hash(SITE, CUR_ID)}'
    scene_store.upsert(SITE, CUR_ID, mc._hash(SITE, CUR_ID), rel, data)
    return rel


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path / 'meta'))
    monkeypatch.setenv('PEOPLE_CACHE_DIR', str(tmp_path / 'people'))
    monkeypatch.delenv('ADMIN_TOKEN', raising=False)
    return TestClient(create_app())


def test_metadata_edit_page_renders_the_stored_fields(client: TestClient, tmp_path: Path) -> None:
    rel = _snapshot(tmp_path)
    page = client.get('/metadata/edit', params={'key': rel})
    assert page.status_code == 200
    assert 'A Cached Scene' in page.text
    assert 'Baby Got Boobs' in page.text
    assert 'Edit Snapshot' in page.text


def test_metadata_edit_page_404s_for_an_unknown_key(client: TestClient) -> None:
    assert client.get('/metadata/edit', params={'key': 'nope/missing'}).status_code == 404


def test_metadata_save_rejects_a_blank_title(client: TestClient, tmp_path: Path) -> None:
    rel = _snapshot(tmp_path)
    r = client.post('/metadata/save', json={'key': rel, 'title': '   '})
    assert r.status_code == 400
    assert 'title' in r.json()['error']


def test_metadata_save_writes_the_edited_fields(client: TestClient, tmp_path: Path) -> None:
    rel = _snapshot(tmp_path)
    r = client.post(
        '/metadata/save',
        json={
            'key': rel,
            'title': 'A Renamed Scene',
            'titleSort': 'Renamed Scene, A',
            'summary': 'New summary.',
            'studio': 'Brazzers',
            'tagline': 'Baby Got Boobs',
            'originallyAvailableAt': '2025-06-07',
            'Genre': ['Anal', 'Teen'],
            'Collection': ['Baby Got Boobs'],
            'Role': ['Jane Doe', 'New Actor'],
            'Director': [],
            'Producer': [],
            'Image': [],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()['ok'] is True

    stored = mc.load_for_edit(r.json()['key'])
    assert stored is not None
    md = stored['MediaContainer']['Metadata'][0]
    assert md['title'] == 'A Renamed Scene'
    assert md['titleSort'] == 'Renamed Scene, A'
    assert md['summary'] == 'New summary.'
    assert md['originallyAvailableAt'] == '2025-06-07'
    assert md['year'] == 2025
    assert [g['tag'] for g in md['Genre']] == ['Anal', 'Teen']
    assert [r['tag'] for r in md['Role']] == ['Jane Doe', 'New Actor']
    assert 'Director' not in md


def test_metadata_save_keeps_a_retained_actors_headshot(client: TestClient, tmp_path: Path) -> None:
    rel = _snapshot(tmp_path)
    r = client.post('/metadata/save', json={'key': rel, 'title': 'A Cached Scene', 'Role': ['Jane Doe']})
    assert r.status_code == 200
    stored = mc.load_for_edit(r.json()['key'])
    assert stored is not None
    assert stored['MediaContainer']['Metadata'][0]['Role'][0]['thumb'].endswith('/images/local/actor/jane-doe.jpg')


def test_people_edit_page_404s_for_an_unknown_file(client: TestClient) -> None:
    assert client.get('/people/edit', params={'filename': 'actor.nobody.jpg'}).status_code == 404


def test_people_save_needs_a_known_file(client: TestClient) -> None:
    r = client.post('/people/save', json={'filename': 'actor.nobody.jpg', 'upstream_url': 'https://x/y.jpg'})
    assert r.status_code == 404


def test_people_save_requires_a_filename(client: TestClient) -> None:
    assert client.post('/people/save', json={'upstream_url': 'https://x/y.jpg'}).status_code == 400


@respx.mock
async def test_metadata_save_keeps_kept_images_and_deletes_dropped_ones(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    image_fetcher._cache.clear()
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    for name in ('a', 'b'):
        respx.get(f'https://cdn.example/{name}.jpg').mock(return_value=httpx.Response(200, content=name.encode() * 4, headers={'content-type': 'image/jpeg'}))

    seeded = PlexMetadataResponse.model_validate(
        {
            'MediaContainer': {
                'identifier': 'phoenixadult',
                'size': 1,
                'Metadata': [
                    {
                        'type': 'movie',
                        'ratingKey': 'rk',
                        'guid': 'g',
                        'title': 'Two Images',
                        'studio': 'Brazzers',
                        'Image': [
                            {'url': 'https://cdn.example/a.jpg', 'type': 'coverPoster'},
                            {'url': 'https://cdn.example/b.jpg', 'type': 'background'},
                        ],
                    }
                ],
            }
        }
    )
    assert await mc.write(SITE, CUR_ID, seeded) is True
    rel = f'{mc._rel_dir(SITE, "Brazzers", "")}/{mc._hash(SITE, CUR_ID)}'
    before = sorted(p.name for p in (tmp_path / rel / 'images').iterdir())
    assert len(before) == 2

    stored = mc.load_for_edit(rel)
    assert stored is not None
    keep = [i for i in stored['MediaContainer']['Metadata'][0]['Image'] if i['type'] == 'background']
    moved = await mc.save_edits(rel, {'title': 'Two Images', 'Image': keep})

    assert moved is not None
    after = sorted(p.name for p in (tmp_path / moved / 'images').iterdir())
    assert len(after) == 1
    served = mc.load_for_edit(moved)
    assert served is not None
    assert [i['type'] for i in served['MediaContainer']['Metadata'][0]['Image']] == ['background']
