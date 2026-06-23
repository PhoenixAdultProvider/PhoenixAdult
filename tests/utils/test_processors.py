from __future__ import annotations

from app.utils.processors.abbreviations import expand_abbreviations
from app.utils.processors.studio_name import normalize_studio
from app.utils.processors.title_case import title_case

# ── title_case ────────────────────────────────────────────────────────────────


def test_title_case_lower_exceptions() -> None:
    assert title_case('the quick brown fox') == 'The Quick Brown Fox'
    assert title_case('a tale of two cities') == 'A Tale of Two Cities'


def test_title_case_upper_and_acronyms() -> None:
    assert title_case('pov scene') == 'POV Scene'
    assert title_case('a vr experience') == 'A VR Experience'


def test_title_case_size_code() -> None:
    assert title_case('xl surprise') == 'XL Surprise'


def test_title_case_manual_correction() -> None:
    assert title_case('cant stop') == "Can't Stop"
    assert title_case('her b day surprise') == 'Her B-Day Surprise'  # two-word form
    assert title_case('bday party') == 'B-Day Party'  # no-space form via MANUAL_CORRECTIONS


def test_title_case_trailing_article_rotation() -> None:
    assert title_case('dog, the') == 'The Dog'


def test_title_case_site_name_preserved() -> None:
    assert title_case('bangbros casting', site_name='BangBros') == 'BangBros Casting'


def test_title_case_strike3_a_game() -> None:
    assert title_case('bringing her a game', scraper_type='strike3') == 'Bringing Her A Game'
    assert title_case("life's a game", scraper_type='strike3') == "Life's A Game"  # accepted trade-off for strike3
    assert title_case('bringing her a game') == 'Bringing Her a Game'  # no correction without scraper


def test_title_case_a_to_an() -> None:
    assert title_case('gets a anal massage') == 'Gets an Anal Massage'
    assert title_case('lonely bored wife gets a anal massage') == 'Lonely Bored Wife Gets an Anal Massage'
    assert title_case('a anal massage') == 'An Anal Massage'
    assert title_case('a big surprise') == 'A Big Surprise'  # no change before consonant


def test_title_case_empty() -> None:
    assert title_case('') == ''


# ── normalize_studio ──────────────────────────────────────────────────────────


def test_studio_alias() -> None:
    assert normalize_studio('pdt') == 'Pretty Dirty Teens'


def test_studio_canonical_snap() -> None:
    assert normalize_studio('bangbros') == 'BangBros'
    assert normalize_studio('BANG BROS') == 'BangBros'


def test_studio_fallback_titlecase() -> None:
    assert normalize_studio('some new studio') == 'Some New Studio'


def test_studio_empty() -> None:
    assert normalize_studio('') == ''


# ── abbreviations ─────────────────────────────────────────────────────────────


def test_abbreviation_expansion() -> None:
    # Prefix-anchored, case-sensitive, primary (followed by space/dot) form.
    assert expand_abbreviations('18og some title').startswith('18OnlyGirls')
    # Non-matching text passes through untouched.
    assert expand_abbreviations('PlainTitle here') == 'PlainTitle here'
