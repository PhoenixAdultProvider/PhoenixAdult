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
    assert title_case('weve got trouble') == "We've Got Trouble"
    assert title_case('What Weve Done') == "What We've Done"
    assert title_case('espanol') == 'Español'
    assert title_case('porno espanol') == 'Porno Español'
    assert title_case('escandalo') == 'Escándalo'


def test_title_case_keeps_a_lowercase_brand_initial_anywhere() -> None:
    assert title_case('ICock') == 'iCock'
    assert title_case('icock') == 'iCock'
    assert title_case('ICock Rides Again') == 'iCock Rides Again'
    assert title_case('The ICock Story') == 'The iCock Story'
    assert title_case('A Scene: icock Returns') == 'A Scene: iCock Returns'
    assert title_case('Ends With icock') == 'Ends with iCock'


def test_title_case_capitalises_a_letter_grade_after_straight() -> None:
    assert title_case('Straight a Student') == 'Straight A Student'
    assert title_case('straight a slut') == 'Straight A Slut'
    assert title_case("straight a's") == "Straight A's"
    assert title_case('My Straight a Sister') == 'My Straight A Sister'


def test_title_case_leaves_the_article_a_alone() -> None:
    assert title_case('Just a Student') == 'Just a Student'
    assert title_case('a game of chess') == 'A Game of Chess'
    assert title_case('straightaway home') == 'Straightaway Home'


def test_title_case_tld_fragment_only_lowercases_as_domain_suffix() -> None:
    assert title_case('lust for co-star') == 'Lust for Co-Star'
    assert title_case('a co-star scene') == 'A Co-Star Scene'
    assert title_case('the co op') == 'The Co Op'
    assert title_case('org chart') == 'Org Chart'
    assert title_case('visit brazzers.com today') == 'Visit Brazzers.com Today'
    assert title_case('watch on xvideos.co') == 'Watch on Xvideos.co'
    assert title_case('filed under news.org') == 'Filed Under News.org'
    assert title_case('Nubiles.net') == 'Nubiles.net'
    assert title_case('Nubiles.tv') == 'Nubiles.tv'
    assert title_case('tv show') == 'TV Show'
    assert title_case('reality tv tonight') == 'Reality TV Tonight'


def test_title_case_name_keeps_single_letters_as_initials() -> None:
    assert title_case('Sybil A Kailena', type='name') == 'Sybil A Kailena'
    assert title_case('Sybil A Alena', type='name') == 'Sybil A Alena'
    assert title_case('Mary J Blige', type='name') == 'Mary J Blige'
    assert title_case('Manaje a Star', type='name') == 'Manaje a Star'
    assert title_case('a game of chess') == 'A Game of Chess'
    assert title_case('an hour of a elephant') == 'An Hour of an Elephant'


def test_title_case_name_keeps_a_trailing_initial_period() -> None:
    assert title_case('Alex D.', type='name') == 'Alex D.'
    assert title_case('Kate G.', type='name') == 'Kate G.'
    assert title_case('Alex Dee.', type='name') == 'Alex Dee'
    assert title_case('the end.') == 'The End'
    assert title_case('plan b.') == 'Plan B'


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


def test_title_case_name_takes_a_honorific_period_only_when_leading() -> None:
    assert title_case('ms juicy', type='name') == 'Ms. Juicy'
    assert title_case('dr love', type='name') == 'Dr. Love'
    assert title_case('summer col', type='name') == 'Summer Col'
    assert title_case('amber lt', type='name') == 'Amber Lt'
    assert title_case('jenna jr', type='name') == 'Jenna Jr'
    assert title_case('summer col') == 'Summer Col.'


def test_title_case_lowercases_loan_particles_only_in_fixed_idioms() -> None:
    assert title_case('Vaginal Creme De La Creme') == 'Vaginal Crème de la Crème'
    assert title_case('CREME DE LA CREME') == 'Crème de la Crème'
    assert title_case('Ohhhhh La La!') == 'Ohhhhh La La!'
    assert title_case('Kill La Kill a XXX Parody') == 'Kill la Kill a XXX Parody'
    assert title_case('Kill La Kill: Satsuki Kiryuin a XXX Parody') == 'Kill la Kill: Satsuki Kiryuin a XXX Parody'
    assert title_case('Cruella De Vil: A XXX Parody') == 'Cruella de Vil: A XXX Parody'
    assert title_case('The Road to El Dorado a XXX Parody') == 'The Road to El Dorado a XXX Parody'
    assert title_case('Mina Von D Initial Fitness Casting') == 'Mina Von D Initial Fitness Casting'


def test_title_case_lowercases_spanish_particles_in_titles_only() -> None:
    assert title_case('Cinco De Mayo') == 'Cinco de Mayo'
    assert title_case('Mapa Del Amor') == 'Mapa del Amor'
    assert title_case('Invasión En Casa') == 'Invasión en Casa'
    assert title_case('Gracias Por Nada') == 'Gracias por Nada'
    assert title_case('En Mi Culo') == 'En mi Culo'
    assert title_case('Bunny De La Cruz', type='name') == 'Bunny De La Cruz'
    assert title_case('Syren De Mer', type='name') == 'Syren De Mer'
    assert title_case('Liza Del Sierra', type='name') == 'Liza Del Sierra'


def test_title_case_con_and_al_stay_capitalised_in_english() -> None:
    assert title_case('the con artist returns') == 'The Con Artist Returns'
    assert title_case('pros and con list') == 'Pros and Con List'
    assert title_case('big al comes over') == 'Big Al Comes Over'
    assert title_case('weird al parody') == 'Weird Al Parody'


def test_title_case_la_lowercases_only_after_a_particle() -> None:
    assert title_case('El Especial De La Manana') == 'El Especial de la Manana'
    assert title_case('Amor En La Playa') == 'Amor en la Playa'
    assert title_case('sings a la carte tune') == 'Sings a la Carte Tune'
    assert title_case("Delta's Day in LA") == "Delta's Day in LA"
    assert title_case('Ooh La La') == 'Ooh La La'


def test_title_case_protects_place_names_from_particle_lowering() -> None:
    assert title_case('Back In Los Angeles') == 'Back in Los Angeles'
    assert title_case('A Trip To Las Vegas') == 'A Trip to Las Vegas'
    assert title_case('The Road To El Dorado') == 'The Road to El Dorado'
    assert title_case('Anna De Ville', type='name') == 'Anna de Ville'


def test_title_case_strap_on_keeps_both_halves_capitalised() -> None:
    assert title_case('Strap-on Into a Threesome') == 'Strap-On Into a Threesome'
    assert title_case("Stuck Slut Gets MILF's Strap-on") == "Stuck Slut Gets MILF's Strap-On"
    assert title_case('Stacked Sister-in-Law') == 'Stacked Sister-in-Law'
    assert title_case('Free-for-All Fuck Lessons') == 'Free-for-All Fuck Lessons'
    assert title_case('Peek-a-Boo and Titties Too') == 'Peek-a-Boo and Titties Too'
    assert title_case('The Live-in Nanny') == 'The Live-in Nanny'


def test_title_case_a_game_is_a_grade_after_a_possessive() -> None:
    assert title_case('Bringing Her A Game') == 'Bringing Her A Game'
    assert title_case('bringing his a game') == 'Bringing His A Game'
    assert title_case('Lets Play a Game Stepdad') == 'Lets Play a Game Stepdad'
    assert title_case('Valentina and Her Husband Have A Game') == 'Valentina and Her Husband Have a Game'


def test_title_case_name_saint_takes_a_period_anywhere() -> None:
    assert title_case('Katie St Ives', type='name') == 'Katie St. Ives'
    assert title_case('sara st james', type='name') == 'Sara St. James'
    assert title_case('Katie St. Ives', type='name') == 'Katie St. Ives'
    assert title_case('st patrick', type='name') == 'St. Patrick'
    assert title_case('1st place', type='name') == '1st Place'
    assert title_case('21st century') == '21st Century'


def test_title_case_trailing_article_rotation() -> None:
    assert title_case('dog, the') == 'The Dog'


def test_title_case_site_name_preserved() -> None:
    assert title_case('bangbros casting', site_name='BangBros') == 'BangBros Casting'


def test_title_case_strike3_a_game() -> None:
    assert title_case('bringing her a game', scraper_type='strike3') == 'Bringing Her A Game'
    assert title_case("life's a game", scraper_type='strike3') == "Life's A Game"
    assert title_case("life's a game") == "Life's a Game"


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


def test_title_case_en_garde_and_spanish_articles() -> None:
    assert title_case('Hard & En Garde') == 'Hard & En Garde'
    assert title_case('hard & en garde') == 'Hard & En Garde'
    assert title_case('Trabajando Por Un Culito De Yoga') == 'Trabajando por un Culito de Yoga'
    assert title_case('Una Noche Loca') == 'Una Noche Loca'
    assert title_case('The Un-Break Up') == 'The Un-Break Up'


def test_title_case_hyphen_compound_first_element_capitalized() -> None:
    assert title_case('the in-her view') == 'The In-Her View'
    assert title_case('The In-Her View') == 'The In-Her View'
    assert title_case('Over-The-Top Anal') == 'Over-the-Top Anal'
    assert title_case('A Run-Of-The-Mill Day') == 'A Run-of-the-Mill Day'
    assert title_case('On-Off Relationship') == 'On-Off Relationship'


def test_title_case_small_word_before_terminal_punctuation_capitalized() -> None:
    assert title_case('who else are we gonna do it with? (family strokes dark)') == 'Who Else Are We Gonna Do It With? (Family Strokes Dark)'
    assert title_case('Who Else Are We Gonna Do It With? (Family Strokes Dark)') == 'Who Else Are We Gonna Do It With? (Family Strokes Dark)'
    assert title_case('come with! right now') == 'Come With! Right Now'
    assert title_case('what is it for? a test') == 'What Is It For? A Test'


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
    assert title_case('The Notorious B. O. O. T. Y') == 'The Notorious B.O.O.T.Y.'
    assert title_case('The Notorious B.O.O.T.Y') == 'The Notorious B.O.O.T.Y.'
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


def test_duckduckgo_drops_its_own_ad_and_internal_links() -> None:
    from phoenixadult.utils.searchengines.duckduckgo import _resolve_ddg_href

    assert _resolve_ddg_href('//duckduckgo.com/l/?uddg=https%3A%2F%2Fx.com%2Fa&rut=z') == 'https://x.com/a'
    assert _resolve_ddg_href('https://duckduckgo.com/y.js?ad_domain=spam.com&ad_provider=bingv7aa') is None
    assert _resolve_ddg_href('https://duckduckgo.com/l/?no_uddg=1') is None
    assert _resolve_ddg_href('https://www.grooby.com/trailers/x') == 'https://www.grooby.com/trailers/x'
    assert _resolve_ddg_href('/relative') is None


def test_title_case_keeps_a_trailing_initialism_period() -> None:
    assert title_case('Fuck P.E.') == 'Fuck P.E.'
    assert title_case('fuck p.e.') == 'Fuck P.E.'
    assert title_case('P.E. Teacher') == 'P.E. Teacher'
    assert title_case('S.W.A.T. Team') == 'S.W.A.T. Team'
    assert title_case('J.R.', type='name') == 'J.R.'
    assert title_case('The End.') == 'The End'
    assert title_case('Plan B.') == 'Plan B'
    assert title_case('a night out.') == 'A Night Out'


def test_search_title_trash_only_strips_real_resolution_tags() -> None:
    assert clean_search_title('scene 4k edition') == 'scene edition'
    assert clean_search_title('movie 2k rip') == 'movie rip'
    assert clean_search_title('clip 8k hdr') == 'clip'
    assert clean_search_title('teenslovemoney 1k pussy') == 'teenslovemoney 1k pussy'
    assert clean_search_title('vr scene 5k') == 'vr scene', 'VR rips ship in 5K/6K/7K'
    assert clean_search_title('immersive 7k pov') == 'immersive pov'
    assert clean_search_title('worth 3k dollars') == 'worth 3k dollars'


def test_title_case_completes_an_undotted_trailing_initialism() -> None:
    assert title_case('J.I.S.M') == 'J.I.S.M.'
    assert title_case('F.B.I') == 'F.B.I.'
    assert title_case('Fuck P.E') == 'Fuck P.E.'
    assert title_case('S.W.A.T') == 'S.W.A.T.'
    assert title_case('J.R', type='name') == 'J.R.'
    assert title_case('Plan B') == 'Plan B'
    assert title_case('Alex D', type='name') == 'Alex D'
    assert title_case('Nubiles.net') == 'Nubiles.net'
    assert title_case('Mr. T') == 'Mr. T'
