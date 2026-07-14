from __future__ import annotations

import pytest

from app.utils.images.image_classifier import classify_image


@pytest.mark.parametrize(
    ('width', 'height', 'expected'),
    [
        (1000, 1400, 'coverPoster'),
        (1000, 1500, 'coverPoster'),
        (1000, 1600, 'coverPoster'),
        (1000, 1399, 'unknown'),
        (1000, 1601, 'unknown'),
        (1920, 1080, 'background'),
        (1000, 999, 'background'),
        (1000, 1000, 'backgroundSquare'),
        (0, 100, 'unknown'),
    ],
)
def test_classify_image(width: int, height: int, expected: str) -> None:
    assert classify_image(width, height).image_class == expected


def test_classify_image_reports_orientation() -> None:
    assert classify_image(1000, 1500).orientation == 'portrait'
    assert classify_image(1920, 1080).orientation == 'landscape'
    assert classify_image(1000, 1000).orientation == 'square'
