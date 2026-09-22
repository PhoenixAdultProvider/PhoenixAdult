from __future__ import annotations

from typing import Any

import pytest

from phoenixadult.mappers.metadata_mapper import build_artwork
from phoenixadult.registry import find_site
from phoenixadult.services import plex_import
from phoenixadult.utils.plex import legacy_guid
from phoenixadult.utils.plex.rating_key import parse_rating_key

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
    assert plex_import._resolve(guid, 'Ignored Studio') == ('Brazzers', 'abc123')


def test_resolve_canonicalizes_the_rating_key_site_token() -> None:
    from phoenixadult.registry import PROVIDER_DEFINITIONS

    guid = f'{PROVIDER_DEFINITIONS[0].plex_identifier}://movie/scene-fit18-abc123.20240115'
    resolved = plex_import._resolve(guid, '')
    assert resolved == ('Fit18', 'abc123'), 'the archive search matches on the canonical site name, not the key token'


def test_resolve_falls_back_to_studio_when_legacy_id_is_unknown() -> None:
    assert plex_import._resolve('com.plexapp.agents.phoenixadult://XYZ|99999999|2025-01-01', 'Fit18') == ('Fit18', 'XYZ')


def test_resolve_gives_up_without_a_site() -> None:
    assert plex_import._resolve('local://12345', '') is None
    assert plex_import._resolve('com.plexapp.agents.phoenixadult://XYZ|99999999|2025-01-01', 'Nope Not A Site') is None


def test_resolve_recovers_an_item_another_agent_matched() -> None:
    from phoenixadult.utils.helpers.ids import b64url_decode

    resolved = plex_import._resolve('com.plexapp.agents.xbmcnfo://AA196?lang=xn', 'Aussie Ass')
    assert resolved is not None
    site_name, cur_id = resolved
    assert site_name == 'Aussie Ass'
    assert b64url_decode(cur_id) == 'AA196'


def test_foreign_cur_id_survives_the_rating_key_round_trip() -> None:
    from phoenixadult.utils.plex.rating_key import to_rating_key

    cur_id = plex_import._foreign_cur_id('com.plexapp.agents.xbmcnfo://AA196?lang=xn')
    assert parse_rating_key(to_rating_key(cur_id, 'Aussie Ass')) == {'site_name': 'aussieass', 'cur_id': cur_id, 'release_date': None}


def test_unresolved_detail_names_the_actual_gap() -> None:
    assert 'no studio' in plex_import._unresolved_detail('local://12345', '')
    assert 'registry' in plex_import._unresolved_detail('local://12345', 'Nope Not A Site')
    assert 'identifier' in plex_import._unresolved_detail('nonsense-guid', 'Aussie Ass')


def test_retired_sites_resolve_to_the_archive_client() -> None:
    site = find_site('Aussie Ass')
    assert site is not None and site.scraper_config.type == 'archive'


def test_archive_never_shadows_a_live_client() -> None:
    import dataclasses

    from phoenixadult.registry import _with_archive
    from phoenixadult.registry.selectors.aggregators.archive import ARCHIVE_SITES

    live = find_site('Brazzers')
    assert live is not None
    stand_in = dataclasses.replace(ARCHIVE_SITES[0], name=live.name)
    merged = _with_archive([live], [stand_in])
    assert [site.scraper_config.type for site in merged] == [live.scraper_config.type]


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
    from phoenixadult.models.metadata import PlexImage

    response = plex_import._build(_item(), 'Fit18', 'CUR1', [PlexImage(url='/cache/x/images/poster-00.jpg', type='coverPoster')])
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
async def test_overwrite_reimports_a_cached_scene(monkeypatch: pytest.MonkeyPatch) -> None:
    report = plex_import.ImportReport(applied=False)
    monkeypatch.setattr(plex_import.scene_store, 'has', lambda _hash: True)
    stub = {'ratingKey': '1', 'title': 'Cached', 'guid': _LEGACY, 'studio': 'Fit18'}
    await plex_import._import_one(None, stub, report, apply=False, overwrite=True)  # type: ignore[arg-type]
    assert report.skipped_existing == 0
    assert report.importable == 1


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
    from phoenixadult.utils import cache as metadata_cache

    monkeypatch.setattr(metadata_cache, 'cache_dir', lambda: str(tmp_path))

    import io

    from PIL import Image as PILImage

    buf = io.BytesIO()
    PILImage.new('RGB', (400, 600)).save(buf, format='JPEG')

    class _Response:
        headers = {'content-type': 'image/jpeg'}
        content = buf.getvalue()

        def raise_for_status(self) -> None:
            return None

    class _Http:
        async def get(self, _url: str) -> _Response:
            return _Response()

    class _Client:
        base = 'http://plex.local:32400'
        http = _Http()

    staging = tmp_path / plex_import._STAGING / 'abc123def456'
    fetched = await plex_import._fetch_candidate(_Client(), 'http://plex.local/thumb')  # type: ignore[arg-type]
    assert fetched is not None
    content, ext, width, height = fetched
    assert (width, height) == (400, 600)
    url = plex_import._stage_image(staging, 'poster-00', content, ext)
    assert url == f'/cache/{plex_import._STAGING}/abc123def456/images/poster-00.jpg'

    resolved = metadata_cache._snapshot_file(url, 'http://provider.local')
    assert resolved is not None
    on_disk, name = resolved
    assert name == 'poster-00.jpg'
    assert on_disk.is_file()


@pytest.mark.asyncio
async def test_stage_artwork_takes_every_candidate_and_types_it(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    from PIL import Image as PILImage

    from phoenixadult.utils import cache as metadata_cache

    monkeypatch.setattr(metadata_cache, 'cache_dir', lambda: str(tmp_path))

    def _jpeg(width: int, height: int) -> bytes:
        buf = io.BytesIO()
        PILImage.new('RGB', (width, height)).save(buf, format='JPEG')
        return buf.getvalue()

    sizes = {'p1': (1000, 1500), 'p2': (1000, 1500), 'wide': (1920, 1080)}

    class _Response:
        def __init__(self, body: bytes) -> None:
            self.content = body
            self.headers = {'content-type': 'image/jpeg'}

        def raise_for_status(self) -> None:
            return None

    class _Http:
        async def get(self, url: str) -> _Response:
            key = next(k for k in sizes if k in url)
            return _Response(_jpeg(*sizes[key]))

    class _Client:
        base = 'http://plex.local:32400'
        http = _Http()

        async def artwork(self, _rating_key: str, kind: str) -> list[dict[str, Any]]:
            if kind == 'posters':
                return [
                    {'ratingKey': 'metadata://posters/agent_p1', 'key': '/p1', 'selected': True},
                    {'ratingKey': 'metadata://posters/agent_p2', 'key': '/p2'},
                ]
            return [
                {'ratingKey': 'metadata://art/agent_p1', 'key': '/p1'},
                {'ratingKey': 'metadata://art/agent_wide', 'key': '/wide', 'selected': True},
            ]

    staging = tmp_path / plex_import._STAGING / 'hash01'
    staged = await plex_import._stage_artwork(_Client(), staging, '51767')  # type: ignore[arg-type]

    assert len(staged) == 3, 'the art copy of agent_p1 is a duplicate and must not be staged twice'
    assert [img.type for img in staged] == ['coverPoster', 'coverPoster', 'background']

    names = sorted(p.name for p in (staging / 'images').iterdir())
    assert names == ['art-00.jpg', 'poster-00.jpg', 'poster-01.jpg'], 'files are named for their shape, not the Plex bucket'


def test_odd_portraits_are_kept_but_ranked_last() -> None:
    from phoenixadult.utils.images.image_classifier import classify_image

    probed = [
        {'url': '/cache/x/images/poster-00.jpg', 'dims': {'width': 427, 'height': 640}, 'image_class': classify_image(427, 640).image_class},
        {'url': '/cache/x/images/poster-14.jpg', 'dims': {'width': 480, 'height': 640}, 'image_class': classify_image(480, 640).image_class},
        {'url': '/cache/x/images/art-27.jpg', 'dims': {'width': 1280, 'height': 720}, 'image_class': classify_image(1280, 720).image_class},
    ]
    images = build_artwork(probed)
    kinds = {img.url: img.type for img in images}
    assert kinds['/cache/x/images/art-27.jpg'] == 'background'
    covers = [img.url for img in images if img.type == 'coverPoster']
    assert covers == ['/cache/x/images/poster-00.jpg', '/cache/x/images/poster-14.jpg'], 'the off-ratio portrait is kept but ranked last'


def test_background_is_promoted_to_poster_only_when_no_poster_exists() -> None:
    landscape_only = [{'url': '/cache/x/images/art-00.jpg', 'dims': {'width': 1280, 'height': 720}, 'image_class': 'background'}]
    promoted = build_artwork(landscape_only)
    assert [img.type for img in promoted] == ['background', 'coverPoster']

    with_poster = [
        {'url': '/cache/x/images/poster-00.jpg', 'dims': {'width': 427, 'height': 640}, 'image_class': 'coverPoster'},
        {'url': '/cache/x/images/art-00.jpg', 'dims': {'width': 1280, 'height': 720}, 'image_class': 'background'},
    ]
    kept = build_artwork(with_poster)
    assert [img.type for img in kept] == ['coverPoster', 'background']


def test_candidate_ref_collapses_the_same_image_across_buckets() -> None:
    poster = {'ratingKey': 'metadata://posters/com.plexapp.agents.phoenixadult_942d'}
    art = {'ratingKey': 'metadata://art/com.plexapp.agents.phoenixadult_942d'}
    assert plex_import._candidate_ref(poster) == plex_import._candidate_ref(art)


def test_candidate_url_handles_every_key_shape() -> None:
    class _C:
        base = 'http://plex.local:32400'

    client = _C()
    assert plex_import._candidate_url(client, {'key': '/library/metadata/1/thumb/2'}) == 'http://plex.local:32400/library/metadata/1/thumb/2'  # type: ignore[arg-type]
    assert plex_import._candidate_url(client, {'key': 'http://cdn/x.jpg'}) == 'http://cdn/x.jpg'  # type: ignore[arg-type]
    photo = plex_import._candidate_url(client, {'ratingKey': 'metadata://posters/agent_abc'})  # type: ignore[arg-type]
    assert photo.startswith('http://plex.local:32400/photo/:/transcode?url=metadata%3A%2F%2Fposters%2Fagent_abc')


def test_report_caps_its_item_list() -> None:
    report = plex_import.ImportReport(applied=False)
    for i in range(plex_import._MAX_ITEMS + 25):
        report.add(plex_import.ItemReport(rating_key=str(i), title='x', status='importable'))
    assert len(report.items) == plex_import._MAX_ITEMS
    assert report.items_truncated == 25


class _OneItemClient:
    def __init__(self, base: str, token: str) -> None:
        self.closed = False

    async def item(self, rating_key: str) -> dict[str, Any]:
        return {'title': 'One Scene', 'guid': _LEGACY, 'studio': 'Fit18'} if rating_key == '42' else {}

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_import_item_imports_exactly_one_scene(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.support import seed_connection

    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setattr(plex_import, 'PlexClient', _OneItemClient)
    monkeypatch.setattr(plex_import.scene_store, 'has', lambda scene_hash: True)
    entry = await plex_import.import_item(seed_connection(), 'tok', '42')
    assert entry.status == 'skipped'
    assert entry.site == 'Fit18'
    assert entry.detail == 'already cached'


@pytest.mark.asyncio
async def test_import_item_reports_a_vanished_item(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.support import seed_connection

    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setattr(plex_import, 'PlexClient', _OneItemClient)
    entry = await plex_import.import_item(seed_connection(), 'tok', '999')
    assert entry.status == 'failed'
    assert 'not found' in entry.detail
