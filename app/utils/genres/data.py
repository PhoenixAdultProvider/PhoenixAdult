from __future__ import annotations

from pathlib import Path
from typing import Any, NamedTuple

from app.utils.fs.reloadable import MtimeCachedJson

_DATA = Path(__file__).parent / '_data' / 'json' / 'genres.json'


class GenreRules(NamedTuple):
    replace_lookup: dict[str, str]
    skip_set: set[str]
    partial_skip: list[str]


def _build(raw: dict[str, Any]) -> GenreRules:
    lookup: dict[str, str] = {}
    for canonical, aliases in raw['replace'].items():
        lookup[canonical.lower()] = canonical
        for alias in aliases:
            lookup[alias.lower()] = canonical
    return GenreRules(lookup, {s.lower() for s in raw['skip']}, [s.lower() for s in raw['partial_skip']])


_RULES: MtimeCachedJson[GenreRules] = MtimeCachedJson(_DATA, _build)


def genre_rules() -> GenreRules:
    """Parsed genres.json, reloaded whenever the file's mtime changes — so edits to
    the skip / partial_skip / replace lists apply without a restart."""
    return _RULES.get()
