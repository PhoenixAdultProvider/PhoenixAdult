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


def test_genres_drop_scraped_actor_names() -> None:
    opts = NormalizeGenresOptions(actors=('Jane Doe', 'John Roe'))
    assert normalize_genres(['Hardcore', 'Jane Doe', 'John Roe'], opts) == ['Hardcore']


def test_genres_actor_match_ignores_case_and_spacing() -> None:
    opts = NormalizeGenresOptions(actors=('Jane Doe',))
    assert normalize_genres(['  jane   doe  '], opts) == []


def test_a_known_genre_survives_an_actor_of_the_same_name() -> None:
    opts = NormalizeGenresOptions(actors=('Amateur',))
    assert normalize_genres(['Amateur'], opts) == ['Amateur']


def test_genres_unaffected_without_actors() -> None:
    assert normalize_genres(['Hardcore', 'Jane Doe']) == normalize_genres(['Hardcore', 'Jane Doe'], NormalizeGenresOptions())
    assert 'Jane Doe' in normalize_genres(['Hardcore', 'Jane Doe'])
