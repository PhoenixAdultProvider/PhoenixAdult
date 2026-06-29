from __future__ import annotations

import json
from pathlib import Path
from typing import Any, NamedTuple

_JSON = Path(__file__).parent / '_data' / 'json'
_ACTORS = _JSON / 'actors.json'


class ActorRules(NamedTuple):
    replace: dict[str, list[str]]
    # Keyed by studio-index (as a string), each a canonical→aliases map.
    replace_studios: dict[str, dict[str, list[str]]]
    # Studio-index (string) → the studio/site names that select that index.
    studio_indexes: dict[str, list[str]]


_cache: tuple[float, ActorRules] | None = None


def actor_rules() -> ActorRules:
    """Parsed actors.json, reloaded whenever the file's mtime changes — so edits to the
    replace / replace_studios / studio_indexes tables apply without a restart."""
    global _cache
    try:
        mtime = _ACTORS.stat().st_mtime
    except OSError:
        mtime = 0.0
    if _cache is None or _cache[0] != mtime:
        raw: dict[str, Any] = json.loads(_ACTORS.read_text(encoding='utf-8'))
        _cache = (mtime, ActorRules(raw['replace'], raw['replace_studios'], raw['studio_indexes']))
    return _cache[1]


ACTORS_JAVBUS_SEARCH: dict[str, list[str]] = json.loads((_JSON / 'actorsJavBusSearch.json').read_text(encoding='utf-8'))


def lookup_javbus_id(actor_name: str) -> str | None:
    if not actor_name:
        return None
    want = actor_name.lower()
    for jav_id, aliases in ACTORS_JAVBUS_SEARCH.items():
        if any(a.lower() == want for a in aliases):
            return jav_id
    return None
