from __future__ import annotations

from typing import Any, NamedTuple

from phoenixadult.utils.fs.reloadable import MtimeCachedJson
from phoenixadult.utils.helpers.data_files import load_data

_ACTORS_PATH = load_data(__file__, 'json/actors.json', kind='path')


class ActorRules(NamedTuple):
    replace: dict[str, list[str]]
    replace_studios: dict[str, dict[str, list[str]]]
    studio_indexes: dict[str, list[str]]
    replace_lookup: dict[str, str]
    replace_studio_lookups: dict[str, dict[str, str]]
    studio_index_lookup: dict[str, tuple[int, str]]


def _alias_lookup(table: dict[str, list[str]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for canonical, aliases in table.items():
        out.setdefault(canonical.lower(), canonical)
        for alias in aliases:
            out.setdefault(alias.lower(), canonical)
    return out


def _build(raw: dict[str, Any]) -> ActorRules:
    studio_lookup: dict[str, tuple[int, str]] = {}
    for pos, (idx, names) in enumerate(raw['studio_indexes'].items()):
        for name in names:
            studio_lookup.setdefault(name.replace(' ', '').lower(), (pos, idx))
    return ActorRules(
        raw['replace'],
        raw['replace_studios'],
        raw['studio_indexes'],
        _alias_lookup(raw['replace']),
        {idx: _alias_lookup(table) for idx, table in raw['replace_studios'].items()},
        studio_lookup,
    )


_RULES: MtimeCachedJson[ActorRules] = MtimeCachedJson(_ACTORS_PATH, _build)


def actor_rules() -> ActorRules:
    return _RULES.get()


ACTORS_JAVBUS_SEARCH: dict[str, list[str]] = load_data(__file__, 'actorsJavBusSearch')


def lookup_javbus_id(actor_name: str) -> str | None:
    if not actor_name:
        return None
    want = actor_name.lower()
    for jav_id, aliases in ACTORS_JAVBUS_SEARCH.items():
        if any(a.lower() == want for a in aliases):
            return jav_id
    return None
