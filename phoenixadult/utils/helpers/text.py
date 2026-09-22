from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from slugify import slugify as _slugify


def slugify(s: str, **kwargs: Any) -> str:
    return _slugify(s, **kwargs)


def dict_values_from_key[T](table: Mapping[Any, T], identifier: str) -> T | None:
    wanted = str(identifier).casefold()
    for key, values in table.items():
        keys = key if isinstance(key, tuple) else (key,)
        if any(str(candidate).casefold() == wanted for candidate in keys):
            return values

    return None


def decensor(text: str, replacements: dict[str, str]) -> str:
    out = text
    for word, correction in replacements.items():
        if word in out:
            out = out.replace(word, correction)
    return out
