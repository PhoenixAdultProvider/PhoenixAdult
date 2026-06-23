from __future__ import annotations

import json
from pathlib import Path

_JSON = Path(__file__).parent / '_data' / 'json'
_actors = json.loads((_JSON / 'actors.json').read_text(encoding='utf-8'))

ACTORS_REPLACE: dict[str, list[str]] = _actors['replace']
# Keyed by studio-index (as a string), each a canonical→aliases map.
ACTORS_REPLACE_STUDIOS: dict[str, dict[str, list[str]]] = _actors['replace_studios']
# Studio-index (string) → the studio/site names that select that index.
ACTORS_STUDIO_INDEXES: dict[str, list[str]] = _actors['studio_indexes']

ACTORS_JAVBUS_SEARCH: dict[str, list[str]] = json.loads((_JSON / 'actorsJavBusSearch.json').read_text(encoding='utf-8'))


def lookup_javbus_id(actor_name: str) -> str | None:
    if not actor_name:
        return None
    want = actor_name.lower()
    for jav_id, aliases in ACTORS_JAVBUS_SEARCH.items():
        if any(a.lower() == want for a in aliases):
            return jav_id
    return None
