from __future__ import annotations

import pytest

import phoenixadult.services.metadata_service as ms
from phoenixadult.models.metadata import PlexMetadataResponse
from phoenixadult.models.provider_info import ProviderInfo
from phoenixadult.services.metadata_service import MetadataService
from phoenixadult.utils.cache import metadata as metadata_cache

PROVIDER = ProviderInfo(id='p', plex_identifier='tv.plex.test.p', title='P', version='1', media_type='movie')
RATING_KEY = 'scene-brazzers-abc123'


def _resp(title: str, *, data18_id: str | None) -> PlexMetadataResponse:
    md: dict[str, object] = {'type': 'movie', 'ratingKey': RATING_KEY, 'guid': 'g', 'title': title, 'studio': 'Brazzers', 'tagline': 'Brazzers Exxtra'}
    if data18_id is not None:
        md['data18'] = {'type': 'scene', 'id': data18_id}
    return PlexMetadataResponse.model_validate({'MediaContainer': {'identifier': 'p', 'size': 1, 'Metadata': [md]}})


@pytest.fixture
def _svc(monkeypatch: pytest.MonkeyPatch) -> MetadataService:
    monkeypatch.setenv('DATA18_ENABLE', 'true')
    svc = MetadataService()
    monkeypatch.setattr(metadata_cache, 'read', lambda site_name, cur_id: _resp('Cached Scene', data18_id=None).model_dump(by_alias=True, exclude_none=True))
    monkeypatch.setattr(svc._scraper, 'decode', lambda cur_id: 'https://www.brazzers.com/scene/1/foo')
    monkeypatch.setattr(ms, 'refresh_cached_snapshot', _async_false)
    return svc


async def _async_false(*args: object, **kwargs: object) -> bool:
    return False


async def test_pull_adopts_fresh_when_data18_found(_svc: MetadataService, monkeypatch: pytest.MonkeyPatch) -> None:
    writes: list[str] = []

    stored = [_resp('Cached Scene', data18_id=None)]

    async def _fake_write(site_name: str, cur_id: str, response: PlexMetadataResponse) -> bool:
        writes.append(response.MediaContainer.Metadata[0].title or '')
        stored.append(response)
        return True

    async def _fake_scrape(*args: object, **kwargs: object) -> PlexMetadataResponse:
        return _resp('Fresh Scene', data18_id='555')

    monkeypatch.setattr(metadata_cache, 'read', lambda site_name, cur_id: stored[-1].model_dump(by_alias=True, exclude_none=True))
    monkeypatch.setattr(metadata_cache, 'write', _fake_write)
    monkeypatch.setattr(_svc, '_scrape', _fake_scrape)

    result = await _svc._fetch_metadata(RATING_KEY, PROVIDER)
    assert result is not None
    assert result.MediaContainer.Metadata[0].title == 'Fresh Scene'
    assert writes == ['Fresh Scene']


async def test_pull_falls_back_to_cache_when_scrape_blocked(_svc: MetadataService, monkeypatch: pytest.MonkeyPatch) -> None:
    writes: list[str] = []

    async def _fake_write(site_name: str, cur_id: str, response: PlexMetadataResponse) -> bool:
        writes.append(response.MediaContainer.Metadata[0].title or '')
        return True

    async def _blocked_scrape(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(metadata_cache, 'write', _fake_write)
    monkeypatch.setattr(_svc, '_scrape', _blocked_scrape)

    result = await _svc._fetch_metadata(RATING_KEY, PROVIDER)
    assert result is not None
    assert result.MediaContainer.Metadata[0].title == 'Cached Scene'
    assert writes == []


async def test_pull_falls_back_to_cache_when_no_match(_svc: MetadataService, monkeypatch: pytest.MonkeyPatch) -> None:
    writes: list[str] = []

    async def _fake_write(site_name: str, cur_id: str, response: PlexMetadataResponse) -> bool:
        writes.append(response.MediaContainer.Metadata[0].title or '')
        return True

    async def _unmatched_scrape(*args: object, **kwargs: object) -> PlexMetadataResponse:
        return _resp('Fresh Scene', data18_id=None)

    monkeypatch.setattr(metadata_cache, 'write', _fake_write)
    monkeypatch.setattr(_svc, '_scrape', _unmatched_scrape)

    result = await _svc._fetch_metadata(RATING_KEY, PROVIDER)
    assert result is not None
    assert result.MediaContainer.Metadata[0].title == 'Cached Scene'
    assert writes == []


async def test_fallback_skips_second_data18_search(_svc: MetadataService, monkeypatch: pytest.MonkeyPatch) -> None:
    seen_skip: list[bool] = []

    async def _spy_refresh(*args: object, **kwargs: object) -> bool:
        seen_skip.append(bool(kwargs.get('skip_data18')))
        return False

    async def _blocked_scrape(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(ms, 'refresh_cached_snapshot', _spy_refresh)
    monkeypatch.setattr(_svc, '_scrape', _blocked_scrape)

    assert await _svc._fetch_metadata(RATING_KEY, PROVIDER) is not None
    assert seen_skip == [True]
