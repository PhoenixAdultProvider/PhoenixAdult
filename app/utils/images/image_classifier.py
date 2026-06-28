from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ImageClass = Literal['coverPoster', 'background', 'unknown']


@dataclass(frozen=True)
class ClassifyResult:
    image_class: ImageClass
    orientation: Literal['portrait', 'landscape', 'square']
    aspect: float


def classify_image(width: int, height: int) -> ClassifyResult:
    if height > width:
        orientation: Literal['portrait', 'landscape', 'square'] = 'portrait'
    elif width > height:
        orientation = 'landscape'
    else:
        orientation = 'square'

    aspect = height / width if width > 0 else 0.0

    if orientation == 'portrait' and 1.4 <= aspect <= 1.6:
        return ClassifyResult('coverPoster', orientation, aspect)
    if orientation == 'landscape':
        return ClassifyResult('background', orientation, aspect)
    return ClassifyResult('unknown', orientation, aspect)
