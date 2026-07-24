from __future__ import annotations

from phoenixadult.utils.genres import NormalizeGenresOptions, normalize_genres


def test_genres_alias_replacement() -> None:
    assert normalize_genres(['anal sex']) == ['Anal']
    assert normalize_genres(['milfs']) == ['MILF']


def test_genres_exact_skip() -> None:
    assert normalize_genres(['scene']) == []


def test_genres_partial_skip() -> None:
    assert normalize_genres(['1080p HD']) == []


def test_genres_unknown_titlecased() -> None:
    assert normalize_genres(['custom tag']) == ['Custom Tag']


def test_genres_dedup() -> None:
    assert normalize_genres(['Anal', 'anal sex', 'ass fucking']) == ['Anal']


def test_genres_heuristic_skip_long_fragment() -> None:
    assert normalize_genres(['this is a very long sentence fragment']) == []


def test_genres_title_echo_skip() -> None:
    opts = NormalizeGenresOptions(title='Custom Tag: The Movie')
    assert normalize_genres(['custom tag'], opts) == []
