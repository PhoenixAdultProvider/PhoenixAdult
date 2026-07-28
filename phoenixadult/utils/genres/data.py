from __future__ import annotations

from typing import Any, NamedTuple

from phoenixadult.utils.fs.reloadable import MtimeCachedJson
from phoenixadult.utils.helpers.helpers import load_data

_DATA = load_data(__file__, 'json/genres.json', kind='path')


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
    return _RULES.get()
