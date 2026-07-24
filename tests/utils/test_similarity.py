from __future__ import annotations

from phoenixadult.utils.processors.similarity import compare_string


def test_levenshtein_case_insensitive_by_default() -> None:
    assert compare_string('ABC', 'abc').levenshtein == 0
    assert compare_string('ABC', 'abc', is_case_insensitive=False).levenshtein == 3


def test_dice_identical_and_disjoint() -> None:
    assert compare_string('hello', 'hello').dice == 1.0
    assert compare_string('abcd', 'wxyz').dice == 0.0


def test_dice_partial() -> None:
    score = compare_string('night', 'nacht').dice
    assert 0.0 < score < 1.0
