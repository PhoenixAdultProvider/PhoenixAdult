from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from phoenixadult.models.provider_info import ProviderInfo
from phoenixadult.models.scrape import SearchResult
from phoenixadult.services import match_service as match_module
from phoenixadult.services import metadata_service as metadata_module
from phoenixadult.services.match_service import MatchRequest, MatchService
from phoenixadult.services.metadata_service import MetadataService
from phoenixadult.services.provider_errors import MalformedRequestError, ProviderUnavailableError
from phoenixadult.utils import db
from phoenixadult.utils.helpers.helpers import b64url_encode
from phoenixadult.utils.http.rate_limit_helper import PacingDeferredError
from phoenixadult.utils.plex.rating_key import to_rating_key

PROVIDER = ProviderInfo(id='phoenixadult', plex_identifier='tv.plex.test.p', title='P', version='1', media_type='movie')
FILENAME = 'nubilefilms.24.01.02.cool.scene.mp4'
RATING_KEY = to_rating_key(b64url_encode('https://nubilefilms.com/video/watch/1'), 'Nubile Films', '2024-01-02')


@pytest.fixture(autouse=True)
def _store_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    monkeypatch.setenv('STATE_DB_PATH', str(tmp_path / 'state.db'))
    yield tmp_path
    db.close()


def _req() -> MatchRequest:
    return MatchRequest(type=1, filename=FILENAME, manual=1, includeAdult=1)


async def test_match_pacing_raises_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = MatchService()

    async def deferred(*args: Any, **kwargs: Any) -> list[SearchResult]:
        raise PacingDeferredError(120.0)

    monkeypatch.setattr(svc, '_search_results', deferred)
    monkeypatch.setattr(svc, '_queue_background_search', lambda *a, **k: None)
    with pytest.raises(ProviderUnavailableError, match='pacing'):
        await svc.match(_req(), PROVIDER)


async def test_match_budget_timeout_raises_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = MatchService()
    monkeypatch.setattr(match_module, 'PLEX_REQUEST_BUDGET', 0.05)

    async def slow(*args: Any, **kwargs: Any) -> None:
        await asyncio.sleep(1)

    monkeypatch.setattr(svc, '_match', slow)
    with pytest.raises(ProviderUnavailableError, match='budget'):
        await svc.match(_req(), PROVIDER)


async def test_match_offline_raises_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = MatchService()

    async def nothing(*args: Any, **kwargs: Any) -> list[SearchResult]:
        return []

    async def offline() -> bool:
        return False

    monkeypatch.setattr(svc, '_search_results', nothing)
    monkeypatch.setattr(match_module, 'transport_failures', lambda: ['nubilefilms.com: ConnectError'])
    monkeypatch.setattr(match_module, 'internet_reachable', offline)
    with pytest.raises(ProviderUnavailableError, match='no network connectivity'):
        await svc.match(_req(), PROVIDER)


async def test_match_site_down_but_online_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = MatchService()

    async def nothing(*args: Any, **kwargs: Any) -> list[SearchResult]:
        return []

    async def online() -> bool:
        return True

    monkeypatch.setattr(svc, '_search_results', nothing)
    monkeypatch.setattr(match_module, 'transport_failures', lambda: ['nubilefilms.com: ConnectError'])
    monkeypatch.setattr(match_module, 'internet_reachable', online)
    result = await svc.match(_req(), PROVIDER)
    assert result.MediaContainer.totalSize == 0


async def test_metadata_malformed_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = MetadataService()
    with pytest.raises(MalformedRequestError, match='unrecognised'):
        await svc.get_metadata('garbage-key', PROVIDER)


async def test_metadata_unknown_site_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = MetadataService()
    with pytest.raises(MalformedRequestError, match='no registry site'):
        await svc.get_metadata('scene-notarealsite123-YWJj', PROVIDER)


async def test_metadata_pacing_raises_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = MetadataService()

    async def deferred(*args: Any, **kwargs: Any) -> None:
        raise PacingDeferredError(120.0)

    monkeypatch.setattr(svc, '_scrape', deferred)
    monkeypatch.setattr(svc, '_queue_background', lambda *a, **k: None)
    with pytest.raises(ProviderUnavailableError, match='pacing'):
        await svc.get_metadata(RATING_KEY, PROVIDER)


async def test_metadata_offline_raises_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = MetadataService()

    async def nothing(*args: Any, **kwargs: Any) -> None:
        return None

    async def offline() -> bool:
        return False

    monkeypatch.setattr(svc, '_scrape', nothing)
    monkeypatch.setattr(metadata_module, 'transport_failures', lambda: ['nubilefilms.com: ConnectError'])
    monkeypatch.setattr(metadata_module, 'internet_reachable', offline)
    with pytest.raises(ProviderUnavailableError, match='no network connectivity'):
        await svc.get_metadata(RATING_KEY, PROVIDER)


async def test_metadata_scrape_miss_while_online_stays_none(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = MetadataService()

    async def nothing(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(svc, '_scrape', nothing)
    assert await svc.get_metadata(RATING_KEY, PROVIDER) is None


async def test_metadata_budget_timeout_raises_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = MetadataService()
    monkeypatch.setattr(metadata_module, 'PLEX_REQUEST_BUDGET', 0.05)

    async def slow(*args: Any, **kwargs: Any) -> None:
        await asyncio.sleep(1)

    monkeypatch.setattr(svc, '_fetch_metadata', slow)
    with pytest.raises(ProviderUnavailableError, match='budget'):
        await svc.get_metadata(RATING_KEY, PROVIDER)
