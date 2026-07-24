from __future__ import annotations

import pytest

from phoenixadult.utils.processors.abbreviations import expand_abbreviations
from phoenixadult.utils.processors.filename_parser import clean_search_title
from phoenixadult.utils.processors.studio_name import normalize_studio
from phoenixadult.utils.processors.title_case import convert_sequence_numbers, title_case, title_sort

# ── Clean_search_title ────────────────────────────────────────────────────────


def test_search_title_trash_builtins_apply_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('SEARCH_TITLE_TRASH', raising=False)
    assert clean_search_title('Cool Scene RARBG 1080p') == 'Cool Scene'


def test_search_title_trash_env_extends_builtins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('SEARCH_TITLE_TRASH', 'MYGROUP')
    assert clean_search_title('Cool Scene RARBG MYGROUP') == 'Cool Scene'


# ── Title_sort ────────────────────────────────────────────────────────────────


def test_title_sort_strips_leading_article() -> None:
    assert title_sort('The Cool Scene') == 'Cool Scene'
    assert title_sort('An Affair') == 'Affair'
    assert title_sort('Cool Scene') is None


def test_title_sort_converts_bounded_numbers() -> None:
    assert title_sort('Cool Scene Part One') == 'Cool Scene Part 1'
    assert title_sort('Cool Scene Part Two') == 'Cool Scene Part 2'
    assert title_sort('Anthology Vol. Three') == 'Anthology Vol. 3'
    assert title_sort('Anthology Volume Twenty One') == 'Anthology Volume 21'
    assert title_sort('Casting Episode Twelve') == 'Casting Episode 12'
    assert title_sort('Story Chapter Five') == 'Story Chapter 5'
    assert title_sort('The Affair Scene Two') == 'Affair Scene 2'
    assert title_sort('Saga Part One Hundred And Five') == 'Saga Part 105'
    assert title_sort('Part One Night Stand') == 'Part 1 Night Stand'
    assert title_sort('The First Part') == '1 Part'
    assert title_sort('Second Scene') == '2 Scene'
    assert title_sort('One Part Two') == '1 Part 2'


def test_title_sort_leaves_unbounded_numbers_alone() -> None:
    assert title_sort('Two for One') is None
    assert title_sort('One Night Stand') is None
    assert title_sort('Two Sisters Part Two') == 'Two Sisters Part 2'


def test_convert_sequence_numbers_keeps_articles() -> None:
    assert convert_sequence_numbers('The Affair Part Two') == 'The Affair Part 2'
    assert convert_sequence_numbers('World War XXX: Part Two') == 'World War XXX: Part 2'
    assert convert_sequence_numbers('The Cool Scene') is None


# ── Title_case ────────────────────────────────────────────────────────────────


def test_title_case_lower_exceptions() -> None:
    assert title_case('the quick brown fox') == 'The Quick Brown Fox'
    assert title_case('a tale of two cities') == 'A Tale of Two Cities'
    assert title_case('girl next door in law') == 'Girl Next Door in Law'
    assert title_case('caught by mom on camera') == 'Caught by Mom on Camera'
    assert title_case('dressed as a maid') == 'Dressed as a Maid'
    assert title_case('tied up at home') == 'Tied Up at Home'


def test_title_case_upper_and_acronyms() -> None:
    assert title_case('pov scene') == 'POV Scene'
    assert title_case('a vr experience') == 'A VR Experience'


def test_title_case_size_code() -> None:
    assert title_case('xl surprise') == 'XL Surprise'


def test_title_case_manual_correction() -> None:
    assert title_case('cant stop') == "Can't Stop"
    assert title_case('her b day surprise') == 'Her B-Day Surprise'
    assert title_case('bday party') == 'B-Day Party'


def test_title_case_tld_fragment_only_lowercases_as_domain_suffix() -> None:
    assert title_case('lust for co-star') == 'Lust for Co-Star'
    assert title_case('a co-star scene') == 'A Co-Star Scene'
    assert title_case('the co op') == 'The Co Op'
    assert title_case('org chart') == 'Org Chart'
    assert title_case('visit brazzers.com today') == 'Visit Brazzers.com Today'
    assert title_case('watch on xvideos.co') == 'Watch on Xvideos.co'
    assert title_case('filed under news.org') == 'Filed Under News.org'


def test_title_case_vs_normalizes_to_one_period() -> None:
    assert title_case('alice vs bob') == 'Alice vs. Bob'
    assert title_case("England vs. Danny's Schlong") == "England vs. Danny's Schlong"
    assert title_case("England vs.. Danny's Schlong") == "England vs. Danny's Schlong"


def test_title_case_possessive_s_ending() -> None:
    assert title_case("Jewels's Jaw-Dropping Anal") == "Jewels' Jaw-Dropping Anal"
    assert title_case("a girl's best friend") == "A Girl's Best Friend"
    assert title_case("the girls' night") == "The Girls' Night"
    assert title_case("it's complicated") == "It's Complicated"


def test_title_case_contraction_suffix_never_lowers_the_leading_word() -> None:
    assert title_case("gets d'd while milf cleans") == "Gets D'd While MILF Cleans"
    assert title_case("d'angelo returns") == "D'Angelo Returns"
    assert title_case("they'd never do that") == "They'd Never Do That"


def test_title_case_honorifics_get_a_period() -> None:
    assert title_case('mr big') == 'Mr. Big'
    assert title_case('dr love') == 'Dr. Love'
    assert title_case('mrs robinson') == 'Mrs. Robinson'
    assert title_case('sgt slaughter') == 'Sgt. Slaughter'
    assert title_case('st patrick') == 'St. Patrick'
    assert title_case('Mr. Smith') == 'Mr. Smith'
    assert title_case('professor x') == 'Professor X'
    assert title_case('1st time') == '1st Time'


def test_title_case_name_skips_honorific_period() -> None:
    assert title_case('summer col', type='name') == 'Summer Col'
    assert title_case('dr love', type='name') == 'Dr Love'
    assert title_case('summer col') == 'Summer Col.'


def test_title_case_trailing_article_rotation() -> None:
    assert title_case('dog, the') == 'The Dog'


def test_title_case_site_name_preserved() -> None:
    assert title_case('bangbros casting', site_name='BangBros') == 'BangBros Casting'


def test_title_case_strike3_a_game() -> None:
    assert title_case('bringing her a game', scraper_type='strike3') == 'Bringing Her A Game'
    assert title_case("life's a game", scraper_type='strike3') == "Life's A Game"
    assert title_case('bringing her a game') == 'Bringing Her a Game'


def test_title_case_a_to_an() -> None:
    assert title_case('gets a anal massage') == 'Gets an Anal Massage'
    assert title_case('lonely bored wife gets a anal massage') == 'Lonely Bored Wife Gets an Anal Massage'
    assert title_case('a anal massage') == 'An Anal Massage'
    assert title_case('a big surprise') == 'A Big Surprise'


def test_title_case_a_stays_before_consonant_sound_vowels() -> None:
    assert title_case('a union nutbuster') == 'A Union Nutbuster'
    assert title_case('a european vacation') == 'A European Vacation'
    assert title_case('a one night stand') == 'A One Night Stand'
    assert title_case('a used toy') == 'A Used Toy'
    assert title_case('a uniform inspection') == 'A Uniform Inspection'


def test_title_case_an_heals_back_before_consonant_sound_vowels() -> None:
    assert title_case('An Union Nutbuster') == 'A Union Nutbuster'
    assert title_case('gets an used toy') == 'Gets a Used Toy'
    assert title_case('an anal massage') == 'An Anal Massage'
    assert title_case('an angel') == 'An Angel'


def test_title_case_subtitle_boundary_after_punctuated_segment() -> None:
    assert title_case('Popping Off - the best of cumshots!') == 'Popping Off - The Best of Cumshots!'
    assert title_case('Gear Up! - the best of sex toys') == 'Gear Up! - The Best of Sex Toys'
    assert title_case('Busted! - the best of getting caught') == 'Busted! - The Best of Getting Caught'
    assert title_case('really? - the truth comes out') == 'Really? - The Truth Comes Out'


def test_title_case_segment_final_small_word_capitalized() -> None:
    assert title_case('stepmom wants to move in - S2:E1') == 'Stepmom Wants to Move In - S2:E1'
    assert title_case('turn me on - the finale') == 'Turn Me On - The Finale'
    assert title_case('girl next door in law') == 'Girl Next Door in Law'


def test_title_case_sequence_marker_colon() -> None:
    assert title_case('Becoming Johnny Sins: Part One') == 'Becoming Johnny Sins: Part One'
    assert title_case('Becoming Johnny Sins - Part Two') == 'Becoming Johnny Sins: Part Two'
    assert title_case('Becoming Johnny Sins Part Three') == 'Becoming Johnny Sins: Part Three'
    assert title_case('Becoming Johnny Sins, Part 2') == 'Becoming Johnny Sins: Part 2'
    assert title_case('Becoming Johnny Sins (Part 2)') == 'Becoming Johnny Sins: Part 2'
    assert title_case('Becoming Johnny Sins-Part 2') == 'Becoming Johnny Sins: Part 2'
    assert title_case('Anthology Vol. 3') == 'Anthology: Vol. 3'
    assert title_case('Casting Episode Twelve') == 'Casting: Episode Twelve'
    assert title_case('Story Chapter IV') == 'Story: Chapter IV'
    assert title_case('Story Chapter V') == 'Story Chapter V'
    assert title_case('The Best Scene 2') == 'The Best Scene 2'
    assert title_case('Anatomy of a Sex Scene 4') == 'Anatomy of a Sex Scene 4'
    assert title_case('My Series - Scene 4') == 'My Series: Scene 4'
    assert title_case('My Series (Scene 4)') == 'My Series: Scene 4'
    assert title_case('X - Part 2') == 'X: Part 2'


def test_title_case_sequence_marker_requires_number() -> None:
    assert title_case('Becoming Part of the Family') == 'Becoming Part of the Family'
    assert title_case('A Part Time Job') == 'A Part Time Job'
    assert title_case('pov scene') == 'POV Scene'
    assert title_case('Part Two') == 'Part Two'
    assert title_case('Awesome Scene XXX') == 'Awesome Scene XXX'


def test_title_case_initialism_collapse() -> None:
    assert title_case('The Notorious B. O. O. T. Y') == 'The Notorious B.O.O.T.Y'
    assert title_case('The Notorious B.O.O.T.Y') == 'The Notorious B.O.O.T.Y'
    assert title_case('S. W. A. T. Team') == 'S.W.A.T. Team'
    assert title_case('Two Girls C. D') == 'Two Girls C. D'


def test_title_case_empty() -> None:
    assert title_case('') == ''


# ── Normalize_studio ──────────────────────────────────────────────────────────


def test_studio_registry_is_the_first_authority() -> None:
    assert normalize_studio('joybear') == 'JoyBear'
    assert normalize_studio('rickys room') == "Ricky's Room"
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


# ── Abbreviations ─────────────────────────────────────────────────────────────


def test_abbreviation_expansion() -> None:
    assert expand_abbreviations('18og some title').startswith('18OnlyGirls')
    assert expand_abbreviations('PlainTitle here') == 'PlainTitle here'
    assert expand_abbreviations('Nubiles here') == 'Nubilesnet here'


def test_abbreviation_expansion_case_insensitive() -> None:
    assert expand_abbreviations('18OG some title').startswith('18OnlyGirls')
    assert expand_abbreviations('BGB some title').startswith('BabyGotBoobs')
    assert expand_abbreviations('nubiles here') == 'Nubilesnet here'


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('compañeros', 'Compañeros'),
        ('niño', 'Niño'),
        ('año nuevo', 'Año Nuevo'),
        ('coño duro', 'Coño Duro'),
        ('café con leche', 'Café Con Leche'),
        ('josé maría', 'José María'),
        ("l'après-midi", "L'Après-Midi"),
        ('straße', 'Straße'),
        ('el doctor primera parte', 'El Doctor Primera Parte'),
    ],
)
def test_title_case_does_not_split_words_on_accented_letters(raw: str, expected: str) -> None:
    assert title_case(raw) == expected


def test_title_case_still_preserves_internal_capitals() -> None:
    assert title_case('LaSirena69') == 'LaSirena69'
    assert title_case('BANGBROS clips') == 'BangBros Clips'


def test_title_case_rotates_a_trailing_article_to_the_front() -> None:
    assert title_case('Big Movie, The') == 'The Big Movie'
    assert title_case('Whore of Wall Street, A') == 'A Whore of Wall Street'
    assert title_case('Movie, The (Disc 2)') != 'The Movie (Disc 2)'


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ("AJ's Fantasy Anal Sex", "A.J.'s Fantasy Anal Sex"),
        ("aj's fantasy anal sex", "A.J.'s Fantasy Anal Sex"),
        ('aj applegate rides', 'A.J. Applegate Rides'),
        ('tj cummings returns', 'T.J. Cummings Returns'),
        ('AJS FANTASY ANAL SEX', 'AJS FANTASY ANAL SEX'),
        ('Ajax Attacks', 'Ajax Attacks'),
        ('Fantasy With A. J. Tonight', 'Fantasy with A.J. Tonight'),
        ('W/ My Best Friend', 'w/ My Best Friend'),
        ('Fun w/AJ', 'Fun w/ A.J.'),
    ],
)
def test_title_case_initial_pair_names(raw: str, expected: str) -> None:
    assert title_case(raw) == expected


def test_spanish_sites_lower_their_particles() -> None:
    assert title_case('clases de mamadas con maria', site_name='FAKings') == 'Clases de Mamadas con Maria'
    assert title_case('vendo a mi novia', site_name='FAKings') == 'Vendo a mi Novia'


def test_spanish_particles_stay_english_elsewhere() -> None:
    assert title_case('a day con el paso', site_name='Brazzers') == 'A Day Con El Paso'


def test_registry_heals_api_cased_aliases() -> None:
    assert normalize_studio('Milf Soup') == 'MILF Soup'
    assert normalize_studio('BIG BUTTS LIKE IT BIG') == 'Big Butts Like It Big'
