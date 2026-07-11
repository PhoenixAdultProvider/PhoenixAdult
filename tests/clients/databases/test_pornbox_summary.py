from __future__ import annotations

import pytest

from app.clients.aggregators.pornbox import _clean_summary


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('AJ FUCKS HER STEPBROTHER.THEY GET CAUGHT', 'A.J. fucks her stepbrother. They get caught.'),
        ('a hot scene w/ aj and friends', 'A hot scene w/ A.J. and friends.'),
        ('MEET A. J. TONIGHT', 'Meet A.J. Tonight.'),
        ('normal summary already. it flows', 'Normal summary already. It flows.'),
        ('ends with punctuation!', 'Ends with punctuation!'),
    ],
)
def test_clean_summary(raw: str, expected: str) -> None:
    assert _clean_summary(raw) == expected
