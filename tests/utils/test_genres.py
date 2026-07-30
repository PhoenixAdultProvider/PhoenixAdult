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


def _canonical_genres() -> list[str]:
    import json
    from pathlib import Path

    from phoenixadult.utils.genres.data import _DATA

    return list(json.loads(Path(_DATA).read_text(encoding='utf-8'))['replace'])


CASING_EXCEPTIONS = {
    'Asian (female)',
    'Asian (male)',
    'Average Body (male)',
    'Caucasian (female)',
    'Caucasian (male)',
    'Ebony (female)',
    'Ebony (male)',
}


def test_every_canonical_genre_matches_the_title_case_rules() -> None:
    from phoenixadult.utils.processors.title_case import title_case

    off_rule = {name for name in _canonical_genres() if name != title_case(name, type='title')}
    assert off_rule == CASING_EXCEPTIONS


def test_a_canonical_genre_survives_a_second_pass_unchanged() -> None:
    canonical = _canonical_genres()
    assert normalize_genres(canonical) == sorted(canonical, key=str.casefold)


def test_the_recased_genres_normalize_to_one_spelling() -> None:
    assert normalize_genres(['cum in mouth']) == ['Cum in Mouth']
    assert normalize_genres(['CUM ON FACE']) == ['Cum on Face']
    assert normalize_genres(['one-on-one']) == ['One-on-One']
    assert normalize_genres(['strap-on']) == ['Strap-On']
    assert normalize_genres(['asian girls']) == ['Asian (female)']
