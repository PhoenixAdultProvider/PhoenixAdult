from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest

from phoenixadult.clients.base import PacingDeferredError, SearchContext, SearchResult
from phoenixadult.models.provider_info import ProviderInfo
from phoenixadult.registry import find_site
from phoenixadult.services.match_service import MatchService
from phoenixadult.utils import db

PROVIDER = ProviderInfo(id='phoenixadult', plex_identifier='tv.plex.test.p', title='P', version='1', media_type='movie')
SITE = find_site('Nubile Films')
assert SITE is not None


@pytest.fixture(autouse=True)
def _store_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    monkeypatch.setenv('STATE_DB_PATH', str(tmp_path / 'state.db'))
    yield tmp_path
    db.close()


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
        return [SearchResult(title=search_data.title, scene_url='https://nubilefilms.com/video/watch/1', cur_id=search_data.title)]

    monkeypatch.setattr(svc._scraper, 'search', fake_search)
    await svc._search_results(_ctx('scene a'), PROVIDER)
    await svc._search_results(_ctx('scene a'), PROVIDER)
    await svc._search_results(_ctx('scene b'), PROVIDER)
    assert calls == ['scene a', 'scene b']


async def test_empty_results_are_never_stored(monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.utils.cache import search_store

    svc = MatchService()
    calls: list[str] = []

    async def empty_search(search_data: SearchContext) -> list[SearchResult]:
        calls.append(search_data.title)
        return []

    monkeypatch.setattr(svc._scraper, 'search', empty_search)
    monkeypatch.setattr(svc, '_is_paced', lambda _ctx: True)
    assert await svc._search_results(_ctx(), PROVIDER) == []
    assert svc._search_memo.get(svc._memo_key(_ctx())) is None
    assert search_store.load(svc._memo_key(_ctx())) is None
    assert await svc._search_results(_ctx(), PROVIDER) == []
    assert calls == ['cool scene', 'cool scene']


async def test_a_transport_failure_never_caches_or_erases_results(monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.utils.cache import search_store
    from phoenixadult.utils.http import connectivity

    svc = MatchService()
    key = svc._memo_key(_ctx())
    search_store.save(key, [SearchResult(title='Kept Scene', scene_url='https://nubilefilms.com/video/watch/9', cur_id='keep')])
    calls: list[str] = []

    async def failing_search(search_data: SearchContext) -> list[SearchResult]:
        calls.append(search_data.title)
        connectivity.note_transport_failure('dns down')
        return []

    monkeypatch.setattr(svc._scraper, 'search', failing_search)
    monkeypatch.setattr(svc, '_is_paced', lambda _ctx: True)
    connectivity.begin_transport_watch()
    orig_load, orig_similar = search_store.load, search_store.load_similar
    monkeypatch.setattr(search_store, 'load', lambda _key: None)
    monkeypatch.setattr(search_store, 'load_similar', lambda _key: None)
    assert await svc._search_results(_ctx(), PROVIDER) == []

    assert svc._search_memo.get(key) is None
    monkeypatch.setattr(search_store, 'load', orig_load)
    monkeypatch.setattr(search_store, 'load_similar', orig_similar)
    stored = search_store.load(key)
    assert stored is not None and stored[0].title == 'Kept Scene'


async def test_memo_key_normalizes_case_and_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = MatchService()
    calls: list[str] = []

    async def fake_search(search_data: SearchContext) -> list[SearchResult]:
        calls.append(search_data.title)
        return [SearchResult(title='Found', scene_url='https://nubilefilms.com/video/watch/1', cur_id='abc')]

    monkeypatch.setattr(svc._scraper, 'search', fake_search)
    await svc._search_results(_ctx('scene a'), PROVIDER)
    await svc._search_results(_ctx('Scene  A'), PROVIDER)
    assert calls == ['scene a']


async def test_search_store_survives_a_fresh_service(monkeypatch: pytest.MonkeyPatch) -> None:
    svc = MatchService()

    async def fake_search(search_data: SearchContext) -> list[SearchResult]:
        return [SearchResult(title='Stored Scene', scene_url='https://nubilefilms.com/video/watch/2', cur_id='xyz')]

    monkeypatch.setattr(svc._scraper, 'search', fake_search)
    await svc._search_results(_ctx('stored scene'), PROVIDER, allow_slow=True)

    fresh = MatchService()

    async def fail_search(search_data: SearchContext) -> list[SearchResult]:
        raise AssertionError('should serve from the search store')

    monkeypatch.setattr(fresh._scraper, 'search', fail_search)
    served = await fresh._search_results(_ctx('Stored  Scene'), PROVIDER)
    assert served is not None and served[0].title == 'Stored Scene'
