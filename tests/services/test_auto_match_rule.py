from __future__ import annotations

import pytest

from phoenixadult.models.metadata import PlexMatchResult
from phoenixadult.services.match_service import AUTO_MATCH_SCORE, auto_match


def _result(title: str, score: float | None) -> PlexMatchResult:
    return PlexMatchResult(ratingKey=f'key-{title}', guid=f'guid-{title}', type='movie', title=title, score=score)


def test_a_single_perfect_result_is_served() -> None:
    chosen, why = auto_match([_result('Wild Scene', 100), _result('Other', 80)])
    assert chosen is not None and chosen.title == 'Wild Scene'
    assert 'serving' in why


def test_nothing_perfect_means_nothing_served() -> None:
    chosen, why = auto_match([_result('Close', 99.9), _result('Far', 40)])
    assert chosen is None and 'no perfect' in why


def test_a_tie_at_the_top_is_ambiguous_and_refused() -> None:
    chosen, why = auto_match([_result('One', 100), _result('Two', 100)])
    assert chosen is None and 'tied' in why


def test_a_higher_score_beats_a_tie_below_it() -> None:
    chosen, _why = auto_match([_result('Best', 120), _result('Tie A', 100), _result('Tie B', 100)])
    assert chosen is not None and chosen.title == 'Best', 'only a tie at the top is ambiguous'


def test_an_empty_result_set_is_refused() -> None:
    chosen, why = auto_match([])
    assert chosen is None and 'no perfect' in why


def test_a_missing_score_is_treated_as_zero() -> None:
    chosen, _why = auto_match([_result('Unscored', None)])
    assert chosen is None


@pytest.mark.parametrize('score', [AUTO_MATCH_SCORE, AUTO_MATCH_SCORE + 0.1])
def test_the_threshold_is_inclusive(score: float) -> None:
    chosen, _why = auto_match([_result('Edge', score)])
    assert chosen is not None
