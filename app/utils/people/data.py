from __future__ import annotations

import json
from pathlib import Path
from typing import Any, NamedTuple

from app.utils.fs.reloadable import MtimeCachedJson

_JSON = Path(__file__).parent / '_data' / 'json'
_ACTORS = _JSON / 'actors.json'


class ActorRules(NamedTuple):
    replace: dict[str, list[str]]
    replace_studios: dict[str, dict[str, list[str]]]
    studio_indexes: dict[str, list[str]]


def _build(raw: dict[str, Any]) -> ActorRules:
    return ActorRules(raw['replace'], raw['replace_studios'], raw['studio_indexes'])


_RULES: MtimeCachedJson[ActorRules] = MtimeCachedJson(_ACTORS, _build)


def actor_rules() -> ActorRules:
    """Parsed actors.json, reloaded whenever the file's mtime changes — so edits to
    the replace / replace_studios / studio_indexes tables apply without a restart."""
    return _RULES.get()


ACTORS_JAVBUS_SEARCH: dict[str, list[str]] = json.loads((_JSON / 'actorsJavBusSearch.json').read_text(encoding='utf-8'))


def lookup_javbus_id(actor_name: str) -> str | None:
    if not actor_name:
        return None
    want = actor_name.lower()
    for jav_id, aliases in ACTORS_JAVBUS_SEARCH.items():
        if any(a.lower() == want for a in aliases):
            return jav_id
    return None
