from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

ImageClass = Literal['coverPoster', 'background', 'backgroundSquare', 'unknown']


@dataclass(frozen=True)
class ClassifyResult:
    image_class: ImageClass
    orientation: Literal['portrait', 'landscape', 'square']
    aspect: float


def classify_image(width: int, height: int) -> ClassifyResult:
    # determine orientation
    orientation: Literal['portrait', 'landscape', 'square']
    if height > width:
        orientation = 'portrait'
    elif width > height:
        orientation = 'landscape'
    else:
        orientation = 'square'

    # aspect is height/width (portrait >1, landscape <1, square ==1)
    aspect = (height / width) if width > 0 else 0.0

    # classify based on orientation and aspect ratio
    classifier: dict[Literal['portrait', 'landscape', 'square'], Callable[[float], ImageClass]] = {
        'portrait': lambda a: 'coverPoster' if 1.4 <= a <= 1.6 else 'unknown',
        'landscape': lambda _: 'background',
        'square': lambda _: 'backgroundSquare',
    }
    image_class: ImageClass = classifier[orientation](aspect)

    return ClassifyResult(image_class, orientation, aspect)
