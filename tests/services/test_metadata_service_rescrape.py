from __future__ import annotations

import time
from typing import Any

import pytest

from phoenixadult.models.metadata import PlexMetadataResponse
from phoenixadult.models.provider_info import ProviderInfo
from phoenixadult.services import scrape_queue
from phoenixadult.services.metadata_service import MetadataService
from phoenixadult.utils.cache import metadata as metadata_cache

PROVIDER = ProviderInfo(id='p', plex_identifier='tv.plex.test.p', title='P', version='1', media_type='movie')
RATING_KEY = 'scene-nubilefilms-abc123'


def _resp() -> PlexMetadataResponse:
    md = {'type': 'movie', 'ratingKey': RATING_KEY, 'guid': 'g', 'title': 'Cached'}
    return PlexMetadataResponse.model_validate({'MediaContainer': {'identifier': 'p', 'size': 1, 'Metadata': [md]}})


async def _queued_call(monkeypatch: pytest.MonkeyPatch, **kwargs: object) -> dict[str, Any]:
    svc = MetadataService()
    calls: dict[str, Any] = {}

    async def _fake_fetch(rating_key: str, provider: ProviderInfo, language: str | None = None, force: bool = False, allow_slow: bool = False) -> None:
        calls.update({'force': force, 'allow_slow': allow_slow})

    monkeypatch.setattr(svc, '_fetch_metadata', _fake_fetch)
    monkeypatch.setattr(metadata_cache, 'read', lambda site_name, cur_id: None)

    jobs: list[Any] = []
    monkeypatch.setattr(scrape_queue, 'enqueue', lambda key, job, **kw: bool(jobs.append(job)) or True)
    svc.queue_snapshot(RATING_KEY, PROVIDER, None, **kwargs)  # type: ignore[arg-type]
    await jobs[0]()
    return calls


async def test_a_rescrape_job_ignores_the_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    assert await _queued_call(monkeypatch, force=True, rescrape=True) == {'force': True, 'allow_slow': True}


async def test_an_ordinary_queued_job_still_serves_the_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    assert await _queued_call(monkeypatch) == {'force': False, 'allow_slow': True}


def test_rescrape_survives_a_restart(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = MetadataService()
    monkeypatch.setattr(metadata_cache, 'read', lambda site_name, cur_id: None)
    replays: list[dict[str, Any]] = []
    monkeypatch.setattr(scrape_queue, 'enqueue', lambda key, job, **kw: bool(replays.append(kw['replay'])) or True)
    svc.queue_snapshot(RATING_KEY, PROVIDER, None, force=True, rescrape=True)
    assert replays[0]['rescrape'] is True


def test_drop_memo_clears_every_language() -> None:
    svc = MetadataService()
    now = time.monotonic()
    svc._memo = {
        (RATING_KEY, 'p', ''): (now, _resp()),
        (RATING_KEY, 'p', 'en'): (now, _resp()),
        (RATING_KEY, 'other', ''): (now, _resp()),
        ('scene-x-y', 'p', ''): (now, _resp()),
    }
    svc.drop_memo(RATING_KEY, PROVIDER)
    assert sorted(svc._memo) == [(RATING_KEY, 'other', ''), ('scene-x-y', 'p', '')]
