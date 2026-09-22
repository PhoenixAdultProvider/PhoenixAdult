from __future__ import annotations

from typing import Any

import pytest

from phoenixadult.models.scrape import SearchResult
from phoenixadult.registry import find_site, get_all_providers
from phoenixadult.services.match_service import MatchRequest, MatchService

SITE = find_site('JoyBear')
assert SITE is not None
PROVIDER = next(p for p in get_all_providers() if p.id == SITE.provider_id)


def _result(title: str, score: float) -> SearchResult:
    return SearchResult(title=title, scene_url=f'https://x/{title}', cur_id=f'id-{title}', score=score)


def _service(results: list[SearchResult]) -> MatchService:
    svc = MatchService()

    async def fake_search(_ctx: Any) -> list[SearchResult]:
        return results

    svc._scraper.search = fake_search  # type: ignore[method-assign]
    return svc


def _request(manual: int) -> MatchRequest:
    return MatchRequest(type=1, filename='JoyBear 2021-03-04 Cool Scene.mp4', manual=manual, includeAdult=1)


@pytest.fixture(autouse=True)
def _auto_match_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('DISABLE_AUTO_MATCH', raising=False)


async def test_auto_returns_single_perfect_match() -> None:
    svc = _service([_result('a', 100), _result('b', 95)])
    resp = await svc.match(_request(manual=0), PROVIDER)
    assert resp.MediaContainer.totalSize == 1
    assert resp.MediaContainer.Metadata[0].score == 100


async def test_auto_empty_without_perfect_match() -> None:
    svc = _service([_result('a', 99), _result('b', 95)])
    resp = await svc.match(_request(manual=0), PROVIDER)
    assert resp.MediaContainer.totalSize == 0


async def test_auto_empty_on_tied_perfect_matches() -> None:
    svc = _service([_result('a', 100), _result('b', 100)])
    resp = await svc.match(_request(manual=0), PROVIDER)
    assert resp.MediaContainer.totalSize == 0


async def test_a_duplicated_result_is_one_match_not_an_ambiguous_tie() -> None:
    svc = _service([_result('a', 100), _result('a', 100)])
    resp = await svc.match(_request(manual=0), PROVIDER)
    assert resp.MediaContainer.totalSize == 1
    assert resp.MediaContainer.Metadata[0].score == 100


async def test_auto_curated_101_beats_tie() -> None:
    svc = _service([_result('a', 101), _result('b', 100)])
    resp = await svc.match(_request(manual=0), PROVIDER)
    assert resp.MediaContainer.totalSize == 1
    assert resp.MediaContainer.Metadata[0].score == 101


async def test_manual_returns_full_sorted_array() -> None:
    svc = _service([_result('a', 95), _result('b', 100)])
    resp = await svc.match(_request(manual=1), PROVIDER)
    assert resp.MediaContainer.totalSize == 2
    scores = [m.score for m in resp.MediaContainer.Metadata]
    assert scores == [100, 95]
