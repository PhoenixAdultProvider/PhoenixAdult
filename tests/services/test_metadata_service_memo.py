from __future__ import annotations

import asyncio

import pytest

from phoenixadult.models.metadata import PlexMetadataResponse
from phoenixadult.models.provider_info import ProviderInfo
from phoenixadult.services.metadata_service import MetadataService

PROVIDER = ProviderInfo(id='p', plex_identifier='tv.plex.test.p', title='P', version='1', media_type='movie')


def _response() -> PlexMetadataResponse:
    return PlexMetadataResponse.model_validate(
        {'MediaContainer': {'identifier': 'p', 'size': 1, 'Metadata': [{'type': 'movie', 'ratingKey': 'rk', 'guid': 'g', 'title': 'T'}]}}
    )


def _counting_service() -> tuple[MetadataService, list[int]]:
    svc = MetadataService()
    calls = [0]

    async def fake_fetch(rating_key: str, provider: ProviderInfo, language: str | None = None, force: bool = False) -> PlexMetadataResponse:
        calls[0] += 1
        await asyncio.sleep(0)
        return _response()

    svc._fetch_metadata = fake_fetch  # type: ignore[method-assign]
    return svc, calls


async def test_sequential_requests_share_one_fetch() -> None:
    svc, calls = _counting_service()
    a = await svc.get_metadata('rk', PROVIDER)
    b = await svc.get_metadata('rk', PROVIDER)
    assert a is b
    assert calls[0] == 1


async def test_concurrent_requests_coalesce() -> None:
    svc, calls = _counting_service()
    a, b = await asyncio.gather(svc.get_metadata('rk', PROVIDER), svc.get_metadata('rk', PROVIDER))
    assert a is b
    assert calls[0] == 1


def _response_with_logo() -> PlexMetadataResponse:
    return PlexMetadataResponse.model_validate(
        {
            'MediaContainer': {
                'identifier': 'p',
                'size': 1,
                'Metadata': [
                    {
                        'type': 'movie',
                        'ratingKey': 'rk',
                        'guid': 'g',
                        'title': 'T',
                        'Image': [{'url': '/cache/x/poster.jpg', 'type': 'coverPoster'}, {'url': '/images/local/logos/b/logo.b.png', 'type': 'clearLogo'}],
                    }
                ],
            }
        }
    )


def test_finalize_strips_clearlogo_when_logos_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.services import metadata_service

    monkeypatch.setattr(metadata_service.logo_cache, 'enabled', lambda: False)
    out = MetadataService()._finalize(_response_with_logo(), PROVIDER, 'rk', cached=True)
    kinds = [img.type for img in out.MediaContainer.Metadata[0].Image or []]
    assert 'clearLogo' not in kinds and 'coverPoster' in kinds


def test_finalize_keeps_clearlogo_when_logos_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.services import metadata_service

    monkeypatch.setattr(metadata_service.logo_cache, 'enabled', lambda: True)
    out = MetadataService()._finalize(_response_with_logo(), PROVIDER, 'rk', cached=True)
    assert 'clearLogo' in [img.type for img in out.MediaContainer.Metadata[0].Image or []]


async def test_distinct_keys_fetch_separately() -> None:
    svc, calls = _counting_service()
    await svc.get_metadata('rk', PROVIDER)
    await svc.get_metadata('rk2', PROVIDER)
    await svc.get_metadata('rk', PROVIDER, language='de')
    assert calls[0] == 3


async def test_failed_fetch_is_not_memoized() -> None:
    svc = MetadataService()
    calls = [0]

    async def fake_fetch(rating_key: str, provider: ProviderInfo, language: str | None = None, force: bool = False) -> PlexMetadataResponse | None:
        calls[0] += 1
        return None

    svc._fetch_metadata = fake_fetch  # type: ignore[method-assign]
    assert await svc.get_metadata('rk', PROVIDER) is None
    assert await svc.get_metadata('rk', PROVIDER) is None
    assert calls[0] == 2


async def test_triple_refresh_forces_a_fresh_fetch() -> None:
    svc, calls = _counting_service()
    await svc.get_metadata('rk', PROVIDER, is_refresh=True)
    await svc.get_metadata('rk', PROVIDER, is_refresh=True)
    await svc.get_metadata('rk', PROVIDER, is_refresh=True)
    assert calls[0] == 2
    await svc.get_metadata('rk', PROVIDER, is_refresh=True)
    assert calls[0] == 2


async def test_images_calls_never_force_refresh() -> None:
    svc, calls = _counting_service()
    for _ in range(5):
        await svc.get_metadata('rk', PROVIDER, is_refresh=False)
    assert calls[0] == 1
