from __future__ import annotations

import re
from pathlib import Path

import pytest

_THEMES = Path(__file__).resolve().parents[2] / 'phoenixadult' / 'routes' / 'html' / 'themes'
_AA = 4.5


def _token(theme: str, name: str) -> str:
    text = (_THEMES / f'{theme}.css').read_text(encoding='utf-8')
    found = re.search(rf'^\s*{re.escape(name)}:\s*(#[0-9a-fA-F]{{6}});', text, re.M)
    assert found, f'{name} is not defined in {theme}.css'
    return found.group(1)


def _relative_luminance(hex_color: str) -> float:
    parts = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in parts]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(a: str, b: str) -> float:
    high, low = sorted((_relative_luminance(a), _relative_luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize('theme', ['midnight', 'forest', 'sky', 'meadow'])
def test_badge_text_is_legible_on_its_own_background(theme: str) -> None:
    background = _token(theme, '--badge-neutral-bg')
    foreground = _token(theme, '--badge-neutral-text')
    got = _contrast(background, foreground)
    assert got >= _AA, f'{theme}: badge text on badge background is {got:.2f}:1, below AA {_AA}:1'


@pytest.mark.parametrize('theme', ['midnight', 'forest', 'sky', 'meadow'])
def test_the_muted_label_color_is_not_used_on_a_filled_badge(theme: str) -> None:
    background = _token(theme, '--badge-neutral-bg')
    label = _token(theme, '--label-text')
    assert _contrast(background, label) < _AA, (
        f'{theme}: --label-text now has enough contrast on a badge. '
        'That is fine, but the version chip picked --badge-neutral-text for a reason — recheck before reverting it.'
    )


def test_the_version_chip_uses_the_paired_token() -> None:
    page = (_THEMES.parent / 'config_ui.html').read_text(encoding='utf-8')
    rule = re.search(r'\.ver \{[^}]*\}', page)
    assert rule and 'var(--badge-neutral-text)' in rule.group(0), 'the version chip must take the badge text color'
