from __future__ import annotations

from typing import Any

import pytest

from phoenixadult.registry import find_site
from phoenixadult.services import plex_import
from phoenixadult.utils.plex import legacy_guid

_LEGACY = 'com.plexapp.agents.phoenixadult://KPS8XwrLBhi6HyW8Wv4yFYDLR6|1336|2025-11-28?lang=en'
_LEGACY_NO_DATE = 'com.plexapp.agents.phoenixadult://2HeX3Zi2vTf1nifUQ6koPrKwVKMd|651?lang=en'


def test_legacy_guid_decodes_both_shapes() -> None:
    assert legacy_guid.decode(_LEGACY) == ('Fit18', 'KPS8XwrLBhi6HyW8Wv4yFYDLR6')
    site, cur_id = legacy_guid.decode(_LEGACY_NO_DATE) or ('', '')
    assert site and cur_id == '2HeX3Zi2vTf1nifUQ6koPrKwVKMd'


def test_legacy_guid_ignores_foreign_agents() -> None:
    assert legacy_guid.decode('com.plexapp.agents.imdb://tt0000001') is None
    assert legacy_guid.payload('local://12345') is None


def test_resolve_prefers_our_own_rating_key() -> None:
    from phoenixadult.registry import PROVIDER_DEFINITIONS

    guid = f'{PROVIDER_DEFINITIONS[0].plex_identifier}://movie/scene-brazzers-abc123.20240115'
    assert plex_import._resolve(guid, 'Ignored Studio') == ('brazzers', 'abc123')


def test_resolve_falls_back_to_studio_when_legacy_id_is_unknown() -> None:
    assert plex_import._resolve('com.plexapp.agents.phoenixadult://XYZ|99999999|2025-01-01', 'Fit18') == ('Fit18', 'XYZ')


def test_resolve_gives_up_without_a_site() -> None:
    assert plex_import._resolve('local://12345', '') is None
    assert plex_import._resolve('com.plexapp.agents.phoenixadult://XYZ|99999999|2025-01-01', 'Nope Not A Site') is None


def test_retired_sites_resolve_to_the_archive_client() -> None:
    site = find_site('Aussie Ass')
    assert site is not None and site.scraper_config.type == 'archive'


def test_archive_never_shadows_a_live_client() -> None:
    site = find_site('Fit18')
    assert site is not None and site.scraper_config.type == 'network18'


def _item() -> dict[str, Any]:
    return {
        'ratingKey': '51767',
        'title': 'A Scene',
        'studio': 'Fit18',
        'summary': 'Some summary.',
        'year': 2025,
        'originallyAvailableAt': '2025-11-28',
        'duration': 1800,
        'Genre': [{'tag': 'Gym'}, {'tag': 'Young'}],
        'Collection': [{'tag': 'Fit18'}],
        'Role': [{'tag': 'Dolly Orchid', 'thumb': 'http://plex/actor.jpg'}],
    }


def test_build_maps_plex_fields_onto_a_response() -> None:
    response = plex_import._build(_item(), 'Fit18', 'CUR1', [('/cache/x/images/poster-00.jpg', 'coverPoster')])
    md = response.MediaContainer.Metadata[0]
    assert md.title == 'A Scene'
    assert md.studio == 'Fit18'
    assert md.originallyAvailableAt == '2025-11-28'
    assert md.contentRating == 'XXX' and md.isAdult is True
    assert [g.tag for g in md.Genre or []] == ['Gym', 'Young']
    assert md.ratingKey.startswith('scene-fit18-CUR1')
    assert md.thumb == '/cache/x/images/poster-00.jpg'


def test_build_drops_actor_thumbs() -> None:
    response = plex_import._build(_item(), 'Fit18', 'CUR1', [])
    role = (response.MediaContainer.Metadata[0].Role or [])[0]
    assert role.tag == 'Dolly Orchid'
    assert role.thumb is None


@pytest.mark.asyncio
async def test_import_skips_already_cached_scenes(monkeypatch: pytest.MonkeyPatch) -> None:
    report = plex_import.ImportReport(applied=True)
    monkeypatch.setattr(plex_import.scene_store, 'has', lambda _hash: True)
    stub = {'ratingKey': '1', 'title': 'Cached', 'guid': _LEGACY, 'studio': 'Fit18'}
    await plex_import._import_one(None, stub, report, apply=True)  # type: ignore[arg-type]
    assert report.skipped_existing == 1
    assert report.imported == 0
    assert report.items[0].status == 'skipped'


@pytest.mark.asyncio
async def test_import_reports_unresolved_scenes(monkeypatch: pytest.MonkeyPatch) -> None:
    report = plex_import.ImportReport(applied=False)
    stub = {'ratingKey': '2', 'title': 'Orphan', 'guid': 'local://9', 'studio': ''}
    await plex_import._import_one(None, stub, report, apply=False)  # type: ignore[arg-type]
    assert report.unresolved == 1
    assert report.items[0].status == 'unresolved'


@pytest.mark.asyncio
async def test_dry_run_counts_without_writing(monkeypatch: pytest.MonkeyPatch) -> None:
    report = plex_import.ImportReport(applied=False)
    monkeypatch.setattr(plex_import.scene_store, 'has', lambda _hash: False)
    stub = {'ratingKey': '3', 'title': 'New', 'guid': _LEGACY, 'studio': 'Fit18'}
    await plex_import._import_one(None, stub, report, apply=False)  # type: ignore[arg-type]
    assert report.importable == 1
    assert report.imported == 0
    assert report.items[0].status == 'importable'


@pytest.mark.asyncio
async def test_staged_image_url_points_at_the_file_it_wrote(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """The staged URL must resolve back through the snapshot writer's own /cache/ lookup, or the
    bytes are silently dropped and the scene lands imageless."""
    from phoenixadult.utils import cache as metadata_cache

    monkeypatch.setattr(metadata_cache, 'cache_dir', lambda: str(tmp_path))

    class _Response:
        headers = {'content-type': 'image/jpeg'}
        content = b'jpegbytes'

        def raise_for_status(self) -> None:
            return None

    class _Http:
        async def get(self, _url: str) -> _Response:
            return _Response()

    class _Client:
        base = 'http://plex.local:32400'
        http = _Http()

    staging = tmp_path / plex_import._STAGING / 'abc123def456'
    url = await plex_import._stage_image(_Client(), staging, '/library/metadata/1/thumb/1', 'poster-00')  # type: ignore[arg-type]
    assert url == f'/cache/{plex_import._STAGING}/abc123def456/images/poster-00.jpg'

    resolved = metadata_cache._snapshot_file(url, 'http://provider.local')
    assert resolved is not None
    on_disk, name = resolved
    assert name == 'poster-00.jpg'
    assert on_disk.is_file() and on_disk.read_bytes() == b'jpegbytes'


def test_report_caps_its_item_list() -> None:
    report = plex_import.ImportReport(applied=False)
    for i in range(plex_import._MAX_ITEMS + 25):
        report.add(plex_import.ItemReport(str(i), 'x', 'importable'))
    assert len(report.items) == plex_import._MAX_ITEMS
    assert report.items_truncated == 25
