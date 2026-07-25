from __future__ import annotations

from typing import Any

from phoenixadult.models.metadata import PlexMetadataResponse
from phoenixadult.models.provider_info import ProviderInfo
from phoenixadult.services.metadata_service import MetadataService
from phoenixadult.services.scraper_router import ScraperRouter
from phoenixadult.utils import cache as mc
from phoenixadult.utils.cache import scene_store
from phoenixadult.utils.helpers.helpers import b64url_encode
from phoenixadult.utils.plex.rating_key import to_rating_key

PROVIDER = ProviderInfo(id='phoenixadult', plex_identifier='tv.plex.agents.custom.phoenixadult', title='P', version='1', media_type='movie')
_BINARY_CUR_ID = '2NXj8cCxarPB5o3ix1TrGWgbS8Ju'


def test_decode_survives_a_cur_id_that_is_not_text() -> None:
    assert ScraperRouter().decode(_BINARY_CUR_ID) == ''


def test_decode_still_returns_a_real_scene_url() -> None:
    assert ScraperRouter().decode(b64url_encode('https://example.com/scene/1')) == 'https://example.com/scene/1'


async def test_an_imported_scene_serves_from_cache_despite_its_legacy_cur_id() -> None:
    site, cur_id = 'Thicc18', _BINARY_CUR_ID
    md: dict[str, Any] = {'type': 'movie', 'ratingKey': 'rk', 'guid': 'g', 'title': 'Imported Scene', 'studio': site}
    data = {'MediaContainer': {'identifier': 'phoenixadult', 'size': 1, 'Metadata': [md]}}
    scene_store.upsert(site, cur_id, mc._hash(site, cur_id), f'archive/{site.lower()}/x', data)

    served = await MetadataService()._fetch_metadata(to_rating_key(cur_id, site), PROVIDER)

    assert isinstance(served, PlexMetadataResponse)
    assert served.MediaContainer.Metadata[0].title == 'Imported Scene'
