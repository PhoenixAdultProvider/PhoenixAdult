from __future__ import annotations

import asyncio

import pytest

from app.clients.base import PacingDeferredError, SearchContext, SearchResult
from app.models.provider_info import ProviderInfo
from app.registry import find_site
from app.services.match_service import MatchService

PROVIDER = ProviderInfo(id='phoenixadult', plex_identifier='tv.plex.test.p', title='P', version='1', media_type='movie')
SITE = find_site('Nubile Films')
assert SITE is not None


def _ctx(title: str = 'cool scene') -> SearchContext:
    return SearchContext(title=title, encoded=title, search_site=SITE.name, site_info=SITE)


async def test_deferred_search_returns_empty_queues_and_memoizes(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = MatchService()
    calls: list[bool] = []

    async def fake_search(search_data: SearchContext) -> list[SearchResult]:
        calls.append(search_data.allow_slow)
        if not search_data.allow_slow:
            raise PacingDeferredError(180.0)
        return [SearchResult(title='Found Scene', scene_url='https://nubilefilms.com/video/watch/1', cur_id='abc')]

    monkeypatch.setattr(svc._scraper, 'search', fake_search)

    ctx = _ctx()
    with pytest.raises(PacingDeferredError):
        await svc._search_results(ctx, PROVIDER)

    svc._queue_background_search(ctx, PROVIDER, 180.0)
    for _ in range(100):
        if len(calls) >= 2:
            break
        await asyncio.sleep(0.01)
    assert calls == [False, True]

    memoed = await svc._search_results(_ctx(), PROVIDER)
    assert memoed is not None and memoed[0].title == 'Found Scene'
    assert calls == [False, True]


async def test_search_memo_absorbs_duplicate_searches(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = MatchService()
    calls: list[str] = []

    async def fake_search(search_data: SearchContext) -> list[SearchResult]:
        calls.append(search_data.title)
        return []

    monkeypatch.setattr(svc._scraper, 'search', fake_search)
    await svc._search_results(_ctx('scene a'), PROVIDER)
    await svc._search_results(_ctx('scene a'), PROVIDER)
    await svc._search_results(_ctx('scene b'), PROVIDER)
    assert calls == ['scene a', 'scene b']
