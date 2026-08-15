from __future__ import annotations

import pytest

from phoenixadult.utils.processors.text_normalize import normalize_text


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('specs. . . just in time', 'specs... just in time'),
        ('wait… then', 'wait... then'),
        ('it`s hers', "it's hers"),
        ('it′s hers', "it's hers"),
        ('it’s hers', "it's hers"),
        ('‘quoted’', "'quoted'"),
        ('“quoted”', '"quoted"'),
        ('„German”', '"German"'),
        ('5″ tall', '5" tall'),
    ],
)
def test_normalize_text_straightens_punctuation(raw: str, expected: str) -> None:
    assert normalize_text(raw) == expected


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('Danny\xa0D  continues', 'Danny D continues'),
        ('a\t\tb', 'a b'),
        ('a\r\nb', 'a\nb'),
        ('one   \n   two', 'one\ntwo'),
        ('  hi  ', 'hi'),
    ],
)
def test_normalize_text_tidies_whitespace(raw: str, expected: str) -> None:
    assert normalize_text(raw) == expected


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('donâ€™t stop', "don't stop"),
        ('Ã©lÃ¨ve', 'élève'),
        ('café stays', 'café stays'),
    ],
)
def test_normalize_text_repairs_mojibake(raw: str, expected: str) -> None:
    assert normalize_text(raw) == expected


def test_normalize_text_leaves_fullwidth_characters_alone() -> None:
    assert normalize_text('ＡＢＣ') == 'ＡＢＣ'


def test_normalize_text_keeps_paragraph_breaks() -> None:
    assert normalize_text('para one\n\npara two') == 'para one\n\npara two'


@pytest.mark.parametrize('raw', ['J. R. R. Tolkien', 'v1.2.3 build', 'End. Next. Then.', 'wait.... ok', 'it\'s "fine"...'])
def test_normalize_text_leaves_these_alone(raw: str) -> None:
    assert normalize_text(raw) == raw


def test_normalize_text_handles_empty() -> None:
    assert normalize_text(None) == ''
    assert normalize_text('') == ''


def test_normalize_text_on_the_real_summary() -> None:
    raw = 'Jimmy Michaels gets a new pair of x-ray specs. . . just in time for his roommate’s girlfriend.'
    assert normalize_text(raw) == "Jimmy Michaels gets a new pair of x-ray specs... just in time for his roommate's girlfriend."


def test_normalize_text_maps_word_private_use_glyphs_to_real_characters() -> None:
    assert normalize_text('making this tape for you! \uf04a') == 'making this tape for you! \u263a'
    assert normalize_text('bullet \uf0b7 point') == 'bullet \u2022 point'
    assert normalize_text('done \uf0fc') == 'done \u2714'


def test_normalize_text_drops_private_use_glyphs_with_no_equivalent() -> None:
    assert normalize_text('nothing renders \ue123here') == 'nothing renders here'


def test_normalize_text_repairs_mojibake_ftfy_cannot_match() -> None:
    assert normalize_text('themâ€"they are') == 'them—they are'
    assert normalize_text('work for us.Â') == 'work for us.'
    assert normalize_text('Âme is a real word') == 'Âme is a real word'


def test_normalize_text_restores_an_apostrophe_lost_to_a_bad_byte() -> None:
    assert normalize_text('money she�s made') == "money she's made"
    assert normalize_text('her tight 5�5 frame') == "her tight 5'5 frame"
    assert normalize_text('caf�') == 'caf'


def test_normalize_text_restores_an_apostrophe_written_as_a_double_quote() -> None:
    assert normalize_text('It ain"t my fault') == "It ain't my fault"
    assert normalize_text('Shit I"d do it again') == "Shit I'd do it again"
    assert normalize_text('if we can"t have it') == "if we can't have it"
    assert normalize_text('open for Carmela"s boobs') == "open for Carmela's boobs"
    assert normalize_text('She is 5"6 and a 24" monitor') == 'She is 5"6 and a 24" monitor'


def test_normalize_text_closes_the_gap_beside_a_quote() -> None:
    assert normalize_text('You say " hi" to me') == 'You say "hi" to me'
    assert normalize_text('Hi "Mr Man " person') == 'Hi "Mr Man" person'
    assert normalize_text('The " quoted " phrase') == 'The "quoted" phrase'
    assert normalize_text('“ smart quotes ” too') == '"smart quotes" too'


def test_normalize_text_treats_an_unclosed_quote_as_an_opening_one() -> None:
    assert normalize_text('Hat " gone now') == 'Hat "gone now'
    assert normalize_text('" leading quote at start') == '"leading quote at start'


def test_normalize_text_leaves_a_quote_that_is_wedged_against_a_word() -> None:
    assert normalize_text('a huge 12" cock and') == 'a huge 12" cock and'
    assert normalize_text('She is 5\'1" and 95 lbs') == 'She is 5\'1" and 95 lbs'
    assert normalize_text('an interview" before convincing') == 'an interview" before convincing'
    assert normalize_text('that "challenge accepted" look') == 'that "challenge accepted" look'
    assert normalize_text('He said "Hello there" loudly') == 'He said "Hello there" loudly'
