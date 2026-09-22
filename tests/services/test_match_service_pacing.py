from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest

from phoenixadult.models.provider_info import ProviderInfo
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import find_site
from phoenixadult.services.match_service import MatchService
from phoenixadult.utils import db
from phoenixadult.utils.http.rate_limit_helper import PacingDeferredError

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


def _stored_ctx(title: str, scene_id: str | None = None) -> SearchContext:
    return SearchContext(title=title, encoded=title, search_site=SITE.name, site_info=SITE, search_date='2022-10-14', scene_id=scene_id)


async def test_stored_results_rescore_live_when_the_filename_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.utils.cache import search_store

    svc = MatchService()
    stale = [SearchResult(title='Winning on Date Night', scene_url='https://nubilefilms.com/video/watch/555', cur_id='abc', score=12.0)]
    search_store.save((SITE.name, 'emelie winning on date night junk words', '2022-10-14', '', ''), stale)

    async def must_not_scrape(search_data: SearchContext) -> list[SearchResult]:
        raise AssertionError('the stored search must be reused, not re-scraped')

    monkeypatch.setattr(svc._scraper, 'search', must_not_scrape)
    results = await svc._search_results(_stored_ctx('winning on date night junk'), PROVIDER)
    assert results is not None and len(results) == 1
    assert results[0].score is not None and results[0].score > 12.0, 'the better filename must raise the stored score'


async def test_an_exact_title_store_hit_also_carries_a_live_score(monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.utils.cache import search_store

    svc = MatchService()
    stale = [SearchResult(title='Winning on Date Night', scene_url='https://nubilefilms.com/video/watch/555', cur_id='abc', score=3.0)]
    search_store.save((SITE.name, 'winning on date night', '2022-10-14', '', ''), stale)

    async def must_not_scrape(search_data: SearchContext) -> list[SearchResult]:
        raise AssertionError('exact hits replay from the store')

    monkeypatch.setattr(svc._scraper, 'search', must_not_scrape)
    results = await svc._search_results(_stored_ctx('winning on date night'), PROVIDER)
    assert results is not None and results[0].score == 100.0, 'a stale stored score never outlives the live one'


async def test_a_scene_id_match_keeps_its_perfect_score(monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.utils.cache import search_store
    from phoenixadult.utils.helpers.ids import pack_cur_id

    svc = MatchService()
    stored = [
        SearchResult(
            title='Totally Different Words', scene_url='https://nubilefilms.com/video/watch/555', cur_id=pack_cur_id(['555', '2022-10-14']), score=100.0
        ),
        SearchResult(title='Winning on Date Night', scene_url='https://nubilefilms.com/video/watch/556', cur_id=pack_cur_id(['556', '2022-10-14']), score=40.0),
    ]
    search_store.save((SITE.name, 'winning on date night extra', '2022-10-14', '555', ''), stored)

    async def must_not_scrape(search_data: SearchContext) -> list[SearchResult]:
        raise AssertionError('stored')

    monkeypatch.setattr(svc._scraper, 'search', must_not_scrape)
    results = await svc._search_results(_stored_ctx('winning on date night', scene_id='555'), PROVIDER)
    assert results is not None
    by_id = {r.cur_id: r for r in results}
    assert by_id[pack_cur_id(['555', '2022-10-14'])].score == 100.0, 'an exact scene-id match is never downgraded by the title'
    other = by_id[pack_cur_id(['556', '2022-10-14'])].score
    assert other is not None and other > 40.0, 'the sibling result is title-rescored'


async def test_an_off_date_stored_result_is_scored_by_date_distance(monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.utils.cache import search_store
    from phoenixadult.utils.helpers.scoring import date_distance_score

    svc = MatchService()
    stored = [
        SearchResult(title='Winning on Date Night', scene_url='https://nubilefilms.com/video/watch/557', cur_id='off', display_date='2022-10-12', score=99.0),
        SearchResult(title='Winning on Date Night', scene_url='https://nubilefilms.com/video/watch/558', cur_id='on', display_date='2022-10-14', score=5.0),
    ]
    search_store.save((SITE.name, 'winning on date night stale words', '2022-10-14', '', ''), stored)

    async def must_not_scrape(search_data: SearchContext) -> list[SearchResult]:
        raise AssertionError('stored')

    monkeypatch.setattr(svc._scraper, 'search', must_not_scrape)
    results = await svc._search_results(_stored_ctx('winning on date night'), PROVIDER)
    assert results is not None
    by_id = {r.cur_id: r for r in results}
    assert by_id['off'].score == float(date_distance_score('2022-10-14', '2022-10-12')), 'a different date scores by date distance'
    assert by_id['on'].score == 100.0, 'a same-date result falls through to the title, which matches exactly here'
    assert results[0].cur_id == 'on', 'the rescored order puts the real match first'


async def test_results_without_scraper_ids_or_dates_fall_through_to_the_title(monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.utils.cache import search_store

    svc = MatchService()
    stored = [SearchResult(title='Winning on Date Night', scene_url='https://nubilefilms.com/video/watch/9', cur_id='!!not-packed!!', score=1.0)]
    search_store.save((SITE.name, 'winning on date night leftover', '2022-10-14', '555', ''), stored)

    async def must_not_scrape(search_data: SearchContext) -> list[SearchResult]:
        raise AssertionError('stored')

    monkeypatch.setattr(svc._scraper, 'search', must_not_scrape)
    results = await svc._search_results(_stored_ctx('winning on date night', scene_id='555'), PROVIDER)
    assert results is not None and results[0].score == 100.0, 'no scraper id and no date means the title decides - and it matches'
