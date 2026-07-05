from __future__ import annotations

import pytest

from app.utils.processors.abbreviations import expand_abbreviations
from app.utils.processors.filename_parser import clean_search_title
from app.utils.processors.studio_name import normalize_studio
from app.utils.processors.title_case import convert_sequence_numbers, title_case, title_sort

# ── clean_search_title ────────────────────────────────────────────────────────


def test_search_title_trash_builtins_apply_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('SEARCH_TITLE_TRASH', raising=False)
    assert clean_search_title('Cool Scene RARBG 1080p') == 'Cool Scene'


def test_search_title_trash_env_extends_builtins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('SEARCH_TITLE_TRASH', 'MYGROUP')
    assert clean_search_title('Cool Scene RARBG MYGROUP') == 'Cool Scene'


# ── title_sort ────────────────────────────────────────────────────────────────


def test_title_sort_strips_leading_article() -> None:
    assert title_sort('The Cool Scene') == 'Cool Scene'
    assert title_sort('An Affair') == 'Affair'
    assert title_sort('Cool Scene') is None  # nothing to change


def test_title_sort_converts_bounded_numbers() -> None:
    assert title_sort('Cool Scene Part One') == 'Cool Scene Part 1'
    assert title_sort('Cool Scene Part Two') == 'Cool Scene Part 2'
    assert title_sort('Anthology Vol. Three') == 'Anthology Vol. 3'
    assert title_sort('Anthology Volume Twenty One') == 'Anthology Volume 21'
    assert title_sort('Casting Episode Twelve') == 'Casting Episode 12'
    assert title_sort('Story Chapter Five') == 'Story Chapter 5'
    assert title_sort('The Affair Scene Two') == 'Affair Scene 2'  # article + number
    assert title_sort('Saga Part One Hundred And Five') == 'Saga Part 105'  # vocab is text2digits' own
    assert title_sort('Part One Night Stand') == 'Part 1 Night Stand'  # number run ends where conversion stops being pure
    assert title_sort('The First Part') == '1 Part'  # number before the marker, in place
    assert title_sort('Second Scene') == '2 Scene'
    assert title_sort('One Part Two') == '1 Part 2'  # both sides of one marker


def test_title_sort_leaves_unbounded_numbers_alone() -> None:
    assert title_sort('Two for One') is None
    assert title_sort('One Night Stand') is None
    assert title_sort('Two Sisters Part Two') == 'Two Sisters Part 2'  # only the bounded number converts


def test_convert_sequence_numbers_keeps_articles() -> None:
    assert convert_sequence_numbers('The Affair Part Two') == 'The Affair Part 2'
    assert convert_sequence_numbers('World War XXX: Part Two') == 'World War XXX: Part 2'
    assert convert_sequence_numbers('The Cool Scene') is None  # article alone is not a conversion


# ── title_case ────────────────────────────────────────────────────────────────


def test_title_case_lower_exceptions() -> None:
    assert title_case('the quick brown fox') == 'The Quick Brown Fox'
    assert title_case('a tale of two cities') == 'A Tale of Two Cities'
    assert title_case('girl next door in law') == 'Girl Next Door in Law'
    assert title_case('caught by mom on camera') == 'Caught by Mom on Camera'
    assert title_case('dressed as a maid') == 'Dressed as a Maid'
    assert title_case('tied up at home') == 'Tied Up at Home'  # 'up' is a particle — stays capitalized


def test_title_case_upper_and_acronyms() -> None:
    assert title_case('pov scene') == 'POV Scene'
    assert title_case('a vr experience') == 'A VR Experience'


def test_title_case_size_code() -> None:
    assert title_case('xl surprise') == 'XL Surprise'


def test_title_case_manual_correction() -> None:
    assert title_case('cant stop') == "Can't Stop"
    assert title_case('her b day surprise') == 'Her B-Day Surprise'  # two-word form
    assert title_case('bday party') == 'B-Day Party'  # no-space form via MANUAL_CORRECTIONS


def test_title_case_honorifics_get_a_period() -> None:
    assert title_case('mr big') == 'Mr. Big'
    assert title_case('dr love') == 'Dr. Love'
    assert title_case('mrs robinson') == 'Mrs. Robinson'
    assert title_case('sgt slaughter') == 'Sgt. Slaughter'
    assert title_case('st patrick') == 'St. Patrick'
    assert title_case('Mr. Smith') == 'Mr. Smith'  # already has a period — no double
    assert title_case('professor x') == 'Professor X'  # full word, not the "prof" abbreviation
    assert title_case('1st time') == '1st Time'  # "st" inside a word is untouched


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


def test_title_case_sequence_marker_colon() -> None:
    assert title_case('Becoming Johnny Sins: Part One') == 'Becoming Johnny Sins: Part One'  # already colon — unchanged
    assert title_case('Becoming Johnny Sins - Part Two') == 'Becoming Johnny Sins: Part Two'
    assert title_case('Becoming Johnny Sins Part Three') == 'Becoming Johnny Sins: Part Three'
    assert title_case('Becoming Johnny Sins, Part 2') == 'Becoming Johnny Sins: Part 2'
    assert title_case('Becoming Johnny Sins (Part 2)') == 'Becoming Johnny Sins: Part 2'
    assert title_case('Becoming Johnny Sins-Part 2') == 'Becoming Johnny Sins: Part 2'  # unspaced dash
    assert title_case('Anthology Vol. 3') == 'Anthology: Vol. 3'
    assert title_case('Casting Episode Twelve') == 'Casting: Episode Twelve'  # spelled number kept as-is
    assert title_case('Story Chapter IV') == 'Story: Chapter IV'  # roman numeral
    assert title_case('The Best Scene 2') == 'The Best: Scene 2'


def test_title_case_sequence_marker_requires_number() -> None:
    assert title_case('Becoming Part of the Family') == 'Becoming Part of the Family'
    assert title_case('A Part Time Job') == 'A Part Time Job'
    assert title_case('pov scene') == 'POV Scene'  # marker with nothing after
    assert title_case('Part Two') == 'Part Two'  # nothing before the marker
    assert title_case('Awesome Scene XXX') == 'Awesome Scene XXX'  # XXX is not a sequence number here


def test_title_case_empty() -> None:
    assert title_case('') == ''


# ── normalize_studio ──────────────────────────────────────────────────────────


def test_studio_registry_is_the_first_authority() -> None:
    assert normalize_studio('joybear') == 'JoyBear'
    assert normalize_studio('rickys room') == "Ricky's Room"  # registry casing/punctuation honored
    assert normalize_studio('RICKYSROOM') == "Ricky's Room"


def test_studio_registry_alias_serves_subsite_display_form() -> None:
    assert normalize_studio('Big Tits At School') == 'Big Tits at School'
    assert normalize_studio('big tits at school') == 'Big Tits at School'
    assert normalize_studio('BigTitsAtSchool') == 'Big Tits at School'
    assert normalize_studio('BIG TITS AT SCHOOL') == 'Big Tits at School'


def test_studio_alias() -> None:
    assert normalize_studio('pdt') == 'Pretty Dirty Teens'
    assert normalize_studio('P.D.T.') == 'Pretty Dirty Teens'
    assert normalize_studio('p d t') == 'Pretty Dirty Teens'


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
