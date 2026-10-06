from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from phoenixadult.models.metadata import PlexMetadataResponse
from phoenixadult.services import snapshot_backfill
from phoenixadult.utils.cache import layout as cache_layout
from phoenixadult.utils.cache import listing as cache_listing
from phoenixadult.utils.cache import metadata as mc
from phoenixadult.utils.cache import scene_store
from phoenixadult.utils.cache.scene_store import SceneFilter
from phoenixadult.utils.images import image_fetcher
from tests.support import authed_client

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
    rel = f'brazzers/{cache_layout.scene_hash_for(SITE, CUR_ID)}'
    scene_store.upsert(SITE, CUR_ID, cache_layout.scene_hash_for(SITE, CUR_ID), rel, data)
    return rel


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path / 'meta'))
    monkeypatch.setenv('IMAGE_DIR', str(tmp_path))
    return authed_client()


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
    rel = cache_layout.bundle_path(cache_layout.scene_hash_for(SITE, CUR_ID))
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


def test_editing_a_headshot_flags_the_scenes_crediting_that_actor(client: TestClient, tmp_path: Path) -> None:
    _snapshot(tmp_path)
    assert scene_store.flag_people_changed('Jane Doe') == ['A Cached Scene']
    assert scene_store.flag_people_changed('Nobody At All') == []


def test_force_refresh_clears_local_thumbs_once(client: TestClient, tmp_path: Path) -> None:
    _snapshot(tmp_path)
    scene_store.flag_people_changed('Jane Doe')

    stored = mc.load_for_edit(f'brazzers/{cache_layout.scene_hash_for(SITE, CUR_ID)}')
    assert stored is not None
    response = PlexMetadataResponse.model_validate(stored)
    assert response.MediaContainer.Metadata[0].Role[0].thumb is not None

    assert mc.drop_stale_people_thumbs(response, SITE, CUR_ID) is True
    assert response.MediaContainer.Metadata[0].Role[0].thumb is None

    again = PlexMetadataResponse.model_validate(stored)
    assert mc.drop_stale_people_thumbs(again, SITE, CUR_ID) is False


def test_backfill_studio_corrects_a_regrouped_site() -> None:
    from phoenixadult.registry import find_site

    site = find_site('Cum4K')
    assert site is not None and site.sub_group is None
    response = PlexMetadataResponse.model_validate(
        {
            'MediaContainer': {
                'identifier': 'p',
                'size': 1,
                'Metadata': [{'type': 'movie', 'ratingKey': 'rk', 'guid': 'g', 'title': 'Old Scene', 'studio': 'Porn Pros', 'tagline': 'Cum4K'}],
            }
        }
    )
    assert snapshot_backfill.backfill_studio(response, site) is True
    md = response.MediaContainer.Metadata[0]
    assert md.studio == 'Cum4K'
    assert md.tagline is None
    assert snapshot_backfill.backfill_studio(response, site) is False


def test_backfill_studio_leaves_a_payload_derived_client_alone() -> None:
    from phoenixadult.registry import find_site

    site = find_site('Adult Time')
    assert site is not None and site.scraper_config.type == 'gammaentother'
    response = PlexMetadataResponse.model_validate(
        {
            'MediaContainer': {
                'identifier': 'p',
                'size': 1,
                'Metadata': [{'type': 'movie', 'ratingKey': 'rk', 'guid': 'g', 'title': 'A Scene', 'studio': 'Some Payload Studio'}],
            }
        }
    )
    assert snapshot_backfill.backfill_studio(response, site) is False
    assert response.MediaContainer.Metadata[0].studio == 'Some Payload Studio'


def test_people_lookup_rejects_an_unknown_source(client: TestClient, tmp_path: Path) -> None:
    r = client.post('/people/lookup', json={'filename': 'actor.nobody.jpg', 'source': 'Not A Source'})
    assert r.status_code == 404


def test_people_lookup_offers_only_remote_sources() -> None:
    from phoenixadult.routes.people_cache_routes import FETCHABLE_SOURCES

    names = [s.name for s in FETCHABLE_SOURCES]
    assert 'Local Storage' not in names
    assert 'IAFD' in names and 'Indexxx' in names
    assert 'Freeones' not in names and 'JAVBus' not in names


def test_people_page_offers_bulk_fetch(client: TestClient) -> None:
    page = client.get('/people')
    assert page.status_code == 200
    assert 'Fetch Images for Shown' in page.text
    assert 'var BULK_SOURCE = "IAFD";' in page.text, 'the fetch source is fixed, not a control'
    assert 'bulkSource' not in page.text
    assert 'Local Storage' not in page.text


def test_bulk_fetch_validates_source_and_selection(client: TestClient) -> None:
    bad_source = client.post('/people/bulk-fetch', json={'source': 'Nope', 'filenames': ['actor.x.jpg']})
    assert bad_source.status_code == 400

    empty = client.post('/people/bulk-fetch', json={'source': 'IAFD', 'filenames': []})
    assert empty.status_code == 400


def _ndjson(payload: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in payload.splitlines() if line.strip()]


def test_bulk_fetch_reports_unknown_people_as_failed(client: TestClient) -> None:
    r = client.post('/people/bulk-fetch', json={'source': 'IAFD', 'filenames': ['actor.not-cached.jpg']})
    assert r.status_code == 200
    body = _ndjson(r.text)[-1]
    assert body['ok'] is True
    assert body['updated'] == 0
    assert body['failed'] == 1


def test_bulk_fetch_streams_progress_per_person(client: TestClient) -> None:
    names = [f'actor.nobody-{n}.jpg' for n in range(3)]
    r = client.post('/people/bulk-fetch', json={'source': 'IAFD', 'filenames': names})
    assert r.status_code == 200
    lines = _ndjson(r.text)
    assert lines[0] == {'source': 'IAFD', 'total': 3}
    assert [line['done'] for line in lines[1:-1]] == [1, 2, 3]
    assert all(line['total'] == 3 for line in lines[1:-1])
    assert lines[-1]['ok'] is True and lines[-1]['failed'] == 3


def test_bulk_fetch_page_renders_a_progress_bar(client: TestClient) -> None:
    page = client.get('/people')
    assert 'bulkProgress' in page.text
    assert 'tr(T.bulk_progress, {done: msg.done, total: msg.total, source})' in page.text


def test_metadata_save_flags_a_hand_entered_data18_id(client: TestClient, tmp_path: Path) -> None:
    rel = _snapshot(tmp_path)
    r = client.post('/metadata/save', json={'key': rel, 'title': 'A Cached Scene', 'data18_id': '987654', 'data18_type': 'scene'})
    assert r.status_code == 200, r.text

    stored = mc.load_for_edit(r.json()['key'])
    assert stored is not None
    assert stored['MediaContainer']['Metadata'][0]['data18'] == {'type': 'scene', 'id': '987654', 'manual': True}

    entries, _total = cache_listing.entries_page(SceneFilter(data18='__manual__'))
    assert [e['data18_id'] for e in entries] == ['987654']
    assert entries[0]['data18_manual'] is True


def test_a_scraped_data18_id_stays_filled_across_a_resave(client: TestClient, tmp_path: Path) -> None:
    rel = _snapshot(tmp_path, data18={'type': 'movie', 'id': '111'})
    r = client.post('/metadata/save', json={'key': rel, 'title': 'A Cached Scene', 'data18_id': '111', 'data18_type': 'movie'})
    assert r.status_code == 200, r.text

    stored = mc.load_for_edit(r.json()['key'])
    assert stored is not None
    assert stored['MediaContainer']['Metadata'][0]['data18'] == {'type': 'movie', 'id': '111'}
    assert cache_listing.entries_page(SceneFilter(data18='__manual__'))[1] == 0
    assert cache_listing.entries_page(SceneFilter(data18='__set__'))[1] == 1


def test_clearing_the_data18_id_drops_the_ref(client: TestClient, tmp_path: Path) -> None:
    rel = _snapshot(tmp_path, data18={'type': 'scene', 'id': '222'})
    r = client.post('/metadata/save', json={'key': rel, 'title': 'A Cached Scene', 'data18_id': ''})
    assert r.status_code == 200, r.text

    stored = mc.load_for_edit(r.json()['key'])
    assert stored is not None
    assert 'data18' not in stored['MediaContainer']['Metadata'][0]
    assert cache_listing.entries_page(SceneFilter(data18='__blank__'))[1] == 1


def test_metadata_edit_page_offers_the_data18_fields(client: TestClient, tmp_path: Path) -> None:
    rel = _snapshot(tmp_path, data18={'type': 'scene', 'id': '333'})
    page = client.get('/metadata/edit', params={'key': rel})
    assert page.status_code == 200
    assert 'f-data18Id' in page.text
    assert 'f-data18Type' in page.text
    assert '"333"' in page.text


def test_saving_a_changed_field_auto_locks_it(client: TestClient, tmp_path: Path) -> None:
    rel = _snapshot(tmp_path)
    r = client.post('/metadata/save', json={'key': rel, 'title': 'Hand Edited Title'})
    assert r.status_code == 200
    locks = scene_store.locks(cache_layout.scene_hash_for(SITE, CUR_ID))
    assert 'title' in locks['fields'], 'a field the admin changed must not be undone by the next refresh'
    assert 'summary' not in locks['fields'], 'untouched fields stay unlocked'


def test_explicit_locks_and_unlocks_round_trip(client: TestClient, tmp_path: Path) -> None:
    rel = _snapshot(tmp_path)
    r = client.post('/metadata/save', json={'key': rel, 'title': 'A Cached Scene', 'lockedFields': ['summary', 'Genre'], 'imagesLocked': True})
    assert r.status_code == 200
    locks = scene_store.locks(cache_layout.scene_hash_for(SITE, CUR_ID))
    assert locks == {'fields': ['Genre', 'summary'], 'imagesLocked': True}

    r = client.post('/metadata/save', json={'key': r.json()['key'], 'title': 'A Cached Scene', 'lockedFields': [], 'imagesLocked': False})
    assert r.status_code == 200
    assert scene_store.locks(cache_layout.scene_hash_for(SITE, CUR_ID)) == {'fields': [], 'imagesLocked': False}


def test_a_refresh_write_cannot_overwrite_locked_fields(client: TestClient, tmp_path: Path) -> None:
    import asyncio

    from phoenixadult.models.metadata import PlexMetadataResponse

    _snapshot(tmp_path)
    scene_hash = cache_layout.scene_hash_for(SITE, CUR_ID)
    scene_store.set_locks(scene_hash, ['title', 'Genre'], False)
    scraped = {
        'MediaContainer': {
            'identifier': 'phoenixadult',
            'size': 1,
            'Metadata': [
                {
                    'type': 'movie',
                    'ratingKey': 'scene-brazzers-cur1',
                    'guid': 'g',
                    'title': 'Scraper Says Otherwise',
                    'studio': 'Brazzers',
                    'tagline': 'Baby Got Boobs',
                    'summary': 'Fresh scraped summary.',
                    'Genre': [{'tag': 'Scraped Genre'}],
                }
            ],
        }
    }
    response = PlexMetadataResponse.model_validate(scraped)
    assert asyncio.run(mc.write(SITE, CUR_ID, response)) is True
    stored = scene_store.load(scene_hash)['MediaContainer']['Metadata'][0]
    assert stored['title'] == 'A Cached Scene', 'the locked title held against the scrape'
    assert [g['tag'] for g in stored['Genre']] == ['Anal'], 'the locked genre list held'
    assert stored['summary'] == 'Fresh scraped summary.', 'unlocked fields updated normally'


def test_the_edit_page_carries_lock_state(client: TestClient, tmp_path: Path) -> None:
    rel = _snapshot(tmp_path)
    scene_store.set_locks(cache_layout.scene_hash_for(SITE, CUR_ID), ['title'], True)
    body = client.get('/metadata/edit', params={'key': rel}).text
    assert '"fields": ["title"]' in body and '"imagesLocked": true' in body
    assert 'installLockUI' in body and 'lockedFields' in body


def test_bulk_fetch_never_claims_success_when_an_item_raises(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import phoenixadult.routes.people_cache_routes as pcr

    async def boom(source: Any, filename: str, entry: Any) -> tuple[str, str]:
        if filename.endswith('-1.jpg'):
            raise RuntimeError('cache_photo exploded')
        return 'missed', filename

    monkeypatch.setattr(pcr, '_fetch_into_cache', boom)
    names = [f'actor.nobody-{n}.jpg' for n in range(3)]
    r = client.post('/people/bulk-fetch', json={'source': 'IAFD', 'filenames': names})
    assert r.status_code == 200
    lines = _ndjson(r.text)
    summary = lines[-1]

    progress = [line for line in lines[1:-1] if 'done' in line]
    assert len(progress) == 3, 'every person must be accounted for even when one blows up'
    assert summary['updated'] + summary['missed'] + summary['failed'] == 3, 'the tally must add up to the batch size'
    assert summary['errors'] == 1, 'an unexpected exception must be counted, not swallowed'
    assert summary['ok'] is False, 'a batch that hit an unexpected error must not report success'
