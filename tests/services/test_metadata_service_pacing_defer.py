from __future__ import annotations

import pytest

from phoenixadult.models.metadata import PlexMetadataResponse
from phoenixadult.models.provider_info import ProviderInfo
from phoenixadult.services import scrape_queue
from phoenixadult.services.metadata_service import MetadataService
from phoenixadult.services.provider_errors import ProviderUnavailableError
from phoenixadult.utils import cache as metadata_cache
from phoenixadult.utils.http.rate_limit_helper import PacingDeferredError

PROVIDER = ProviderInfo(id='p', plex_identifier='tv.plex.test.p', title='P', version='1', media_type='movie')
RATING_KEY = 'scene-nubilefilms-abc123'


def _resp(title: str) -> PlexMetadataResponse:
    md = {'type': 'movie', 'ratingKey': RATING_KEY, 'guid': 'g', 'title': title, 'studio': 'Nubile Films'}
    return PlexMetadataResponse.model_validate({'MediaContainer': {'identifier': 'p', 'size': 1, 'Metadata': [md]}})


async def test_deferred_scrape_fails_fast_and_queues(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = MetadataService()
    monkeypatch.setattr(metadata_cache, 'read', lambda site_name, cur_id: None)
    monkeypatch.setattr(svc._scraper, 'decode', lambda cur_id: 'https://nubilefilms.com/video/watch/1')

    async def _deferring_scrape(*args: object, **kwargs: object) -> PlexMetadataResponse:
        if kwargs.get('allow_slow'):
            return _resp('Background Scene')
        raise PacingDeferredError(180.0)

    writes: list[str] = []

    async def _fake_write(site_name: str, cur_id: str, response: PlexMetadataResponse) -> bool:
        writes.append(response.MediaContainer.Metadata[0].title or '')
        return True

    monkeypatch.setattr(svc, '_scrape', _deferring_scrape)
    monkeypatch.setattr(metadata_cache, 'write', _fake_write)

    queued: list[str] = []
    real_enqueue = scrape_queue.enqueue
    monkeypatch.setattr(scrape_queue, 'enqueue', lambda key, job, **kw: queued.append(key) or real_enqueue(key, job, **kw))

    with pytest.raises(ProviderUnavailableError, match='pacing'):
        await svc._fetch_metadata(RATING_KEY, PROVIDER)
    assert queued == [f'p:{RATING_KEY}']

    import asyncio

    for _ in range(50):
        if writes:
            break
        await asyncio.sleep(0.01)
    assert writes == ['Background Scene']
