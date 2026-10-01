from __future__ import annotations

from typing import Any

import pytest

from phoenixadult.models.metadata import PlexMetadataResponse
from phoenixadult.models.provider_info import ProviderInfo
from phoenixadult.registry import find_site
from phoenixadult.services import snapshot_backfill
from phoenixadult.services.metadata_service import MetadataService, _Update, refresh_cached_snapshot
from phoenixadult.utils.cache import layout as cache_layout
from phoenixadult.utils.cache import locks as cache_locks
from phoenixadult.utils.cache import metadata as metadata_cache
from phoenixadult.utils.cache import people_backfill, scene_store, text_rules

PROVIDER = ProviderInfo(id='p', plex_identifier='tv.plex.test.p', title='P', version='1', media_type='movie')
SITE = 'Lock Studio'
CUR = 'lock-cur-1'


def _payload(**overrides: Any) -> dict[str, Any]:
    md: dict[str, Any] = {
        'type': 'movie',
        'ratingKey': 'rk-lock',
        'guid': 'g-lock',
        'title': 'Original Title',
        'summary': 'Original summary.',
        'studio': SITE,
        'tagline': 'Original Tagline',
        'originallyAvailableAt': '2024-01-01',
        'Genre': [{'tag': 'Original Genre'}],
        'Role': [{'tag': 'Original Actor'}],
        'Image': [
            {'url': '/cache/scenes/aa/lock/images/img-01.jpg', 'type': 'coverPoster'},
            {'url': '/cache/scenes/aa/lock/images/img-02.jpg', 'type': 'background'},
        ],
        'thumb': '/cache/scenes/aa/lock/images/img-01.jpg',
        'art': '/cache/scenes/aa/lock/images/img-02.jpg',
    }
    md.update(overrides)
    return {'MediaContainer': {'identifier': 'i', 'size': 1, 'Metadata': [md]}}


def _seed(**overrides: Any) -> str:
    scene_hash = cache_layout.scene_hash_for(SITE, CUR)
    scene_store.upsert(SITE, CUR, scene_hash, cache_layout.bundle_path(scene_hash), _payload(**overrides))
    return scene_hash


def test_locks_survive_a_wholesale_upsert() -> None:
    scene_hash = _seed()
    scene_store.set_locks(scene_hash, ['title', 'Genre'], True)
    scene_store.upsert(SITE, CUR, scene_hash, cache_layout.bundle_path(scene_hash), _payload(title='Scraped Over'))
    assert scene_store.locks(scene_hash) == {'fields': ['Genre', 'title'], 'imagesLocked': True}


def test_a_locked_image_round_trips_through_the_payload() -> None:
    scene_hash = _seed()
    payload = _payload()
    payload['MediaContainer']['Metadata'][0]['Image'][0]['locked'] = True
    scene_store.upsert(SITE, CUR, scene_hash, cache_layout.bundle_path(scene_hash), payload)
    loaded = scene_store.load(scene_hash)
    images = loaded['MediaContainer']['Metadata'][0]['Image']
    assert any(i.get('locked') for i in images) and not all(i.get('locked') for i in images)


def _fresh_meta() -> dict[str, Any]:
    return _payload(
        title='Scraped Title',
        summary='Scraped summary.',
        Genre=[{'tag': 'Scraped Genre'}],
        Image=[{'url': 'https://site/new-poster.jpg', 'type': 'coverPoster'}],
        thumb='https://site/new-poster.jpg',
    )['MediaContainer']['Metadata'][0]


def test_the_merge_holds_locked_fields_against_a_fresh_scrape() -> None:
    scene_hash = _seed()
    previous = scene_store.load(scene_hash)
    meta = _fresh_meta()
    held = cache_locks.apply_locks(meta, previous, {'fields': ['title', 'Genre'], 'imagesLocked': False})
    assert 'title' in held and 'Genre' in held
    assert meta['title'] == 'Original Title'
    assert [g['tag'] for g in meta['Genre']] == ['Original Genre']
    assert meta['summary'] == 'Scraped summary.', 'unlocked fields still update'


def test_the_global_image_lock_freezes_the_exact_set() -> None:
    scene_hash = _seed()
    previous = scene_store.load(scene_hash)
    meta = _fresh_meta()
    cache_locks.apply_locks(meta, previous, {'fields': [], 'imagesLocked': True})
    assert [i['url'] for i in meta['Image']] == ['/cache/scenes/aa/lock/images/img-01.jpg', '/cache/scenes/aa/lock/images/img-02.jpg']
    assert meta['thumb'] == '/cache/scenes/aa/lock/images/img-01.jpg'
    assert meta['art'] == '/cache/scenes/aa/lock/images/img-02.jpg'


def test_an_individually_locked_image_survives_while_siblings_are_replaced() -> None:
    scene_hash = cache_layout.scene_hash_for(SITE, CUR)
    payload = _payload()
    payload['MediaContainer']['Metadata'][0]['Image'][1]['locked'] = True
    scene_store.upsert(SITE, CUR, scene_hash, cache_layout.bundle_path(scene_hash), payload)
    previous = scene_store.load(scene_hash)
    meta = _fresh_meta()
    cache_locks.apply_locks(meta, previous, {'fields': [], 'imagesLocked': False})
    urls = [i['url'] for i in meta['Image']]
    assert '/cache/scenes/aa/lock/images/img-02.jpg' in urls, 'the locked image is pinned'
    assert 'https://site/new-poster.jpg' in urls, 'fresh siblings still arrive'
    assert '/cache/scenes/aa/lock/images/img-01.jpg' not in urls, 'the unlocked sibling is replaced'


def test_reapply_text_rules_skips_locked_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.models.metadata import PlexMetadataResponse

    response = PlexMetadataResponse.model_validate(_payload(title='all lower needs recasing'))
    changed = text_rules.reapply_text_rules(response, None, locked={'title'})
    assert response.MediaContainer.Metadata[0].title == 'all lower needs recasing', 'a locked title is never recased'
    response2 = PlexMetadataResponse.model_validate(_payload(title='all lower needs recasing'))
    text_rules.reapply_text_rules(response2, None, locked=set())
    assert response2.MediaContainer.Metadata[0].title != 'all lower needs recasing', 'unlocked titles still recase'
    assert changed in (True, False)


async def test_a_fresh_scrape_serves_the_stored_copy_that_honours_locks(monkeypatch: pytest.MonkeyPatch) -> None:
    fresh = PlexMetadataResponse.model_validate(_payload(title='Scraped Title'))
    stored = _payload(title='Locked Title')

    async def _write(site_name: str, cur_id: str, response: PlexMetadataResponse) -> bool:
        return True

    monkeypatch.setattr(metadata_cache, 'write', _write)
    monkeypatch.setattr(metadata_cache, 'read', lambda site_name, cur_id: stored)
    update = _Update('rk', PROVIDER, find_site('Brazzers'), CUR, 'https://x/1', None, None, None, False)  # type: ignore[arg-type]
    served = await MetadataService()._store(fresh, update)
    assert served.MediaContainer.Metadata[0].title == 'Locked Title'


async def test_a_disabled_cache_serves_the_scrape_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    fresh = PlexMetadataResponse.model_validate(_payload(title='Scraped Title'))

    async def _write(site_name: str, cur_id: str, response: PlexMetadataResponse) -> bool:
        return False

    monkeypatch.setattr(metadata_cache, 'write', _write)
    update = _Update('rk', PROVIDER, find_site('Brazzers'), CUR, 'https://x/1', None, None, None, False)  # type: ignore[arg-type]
    assert await MetadataService()._store(fresh, update) is fresh


async def test_a_locked_studio_is_not_restudioed(monkeypatch: pytest.MonkeyPatch) -> None:
    scene_hash = _seed()
    scene_store.set_locks(scene_hash, ['studio'], False)
    called: list[str] = []
    monkeypatch.setattr(snapshot_backfill, 'backfill_studio', lambda response, site: called.append('studio') or True)
    monkeypatch.setattr(people_backfill, 'backfill_people_images', _async_false)
    response = PlexMetadataResponse.model_validate(_payload())
    site = find_site('Brazzers')
    assert site is not None
    monkeypatch.setattr(cache_layout, 'scene_hash_for', lambda site_name, cur_id: scene_hash)
    await refresh_cached_snapshot(response, site, CUR, skip_data18=True)
    assert called == []


async def _async_false(*args: object, **kwargs: object) -> bool:
    return False
