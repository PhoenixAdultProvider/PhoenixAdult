from __future__ import annotations

import pytest

from app.utils.processors.text_normalize import normalize_text


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
