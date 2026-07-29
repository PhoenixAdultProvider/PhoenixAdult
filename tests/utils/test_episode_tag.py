from __future__ import annotations

import pytest

from phoenixadult.utils.processors.episode_tag import strip_episode_tag


@pytest.mark.parametrize(
    ('raw', 'want'),
    [
        ('Stepmom Wants to Move In - S2:E1', 'Stepmom Wants to Move In'),
        ('Title - S10:E12', 'Title'),
        ('Title - S1E2', 'Title'),
        ('S1E3: Sneaky, Bratty Lil Stepsis', 'Sneaky, Bratty Lil Stepsis'),
        ('S1:E3: Sneaky, Bratty Lil Stepsis', 'Sneaky, Bratty Lil Stepsis'),
        ('s1e3 - Lowercase Tag', 'Lowercase Tag'),
        ('S10E12 - Something', 'Something'),
    ],
)
def test_an_episode_tag_is_stripped_from_either_end(raw: str, want: str) -> None:
    assert strip_episode_tag(raw) == want


@pytest.mark.parametrize(
    'raw',
    [
        'Home - Sweet Home',
        'No Tag Here',
        'S1E3 Missing Separator',
        'Se7en: A Real Title',
        'Episode 3: A Real Title',
    ],
)
def test_a_title_without_a_tag_is_left_alone(raw: str) -> None:
    assert strip_episode_tag(raw) == raw


def test_an_empty_title_stays_empty() -> None:
    assert strip_episode_tag('') == ''
