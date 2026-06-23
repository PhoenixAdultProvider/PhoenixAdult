from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from rapidfuzz.distance import Levenshtein


@dataclass(frozen=True)
class StringComparison:
    dice: float
    levenshtein: int


def _dice(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if len(a) < 2 or len(b) < 2:
        return 0.0
    ba = Counter(a[i : i + 2] for i in range(len(a) - 1))
    bb = Counter(b[i : i + 2] for i in range(len(b) - 1))
    overlap = sum((ba & bb).values())
    return 2 * overlap / (sum(ba.values()) + sum(bb.values()))


def compare_string(a: str, b: str, is_case_insensitive: bool = True) -> StringComparison:
    a = a or ''
    b = b or ''
    if is_case_insensitive:
        a = a.lower()
        b = b.lower()
    return StringComparison(dice=_dice(a, b), levenshtein=Levenshtein.distance(a, b))
