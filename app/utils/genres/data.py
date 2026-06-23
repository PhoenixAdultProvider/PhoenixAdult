from __future__ import annotations

import json
from pathlib import Path

_DATA = Path(__file__).parent / '_data' / 'json' / 'genres.json'
_raw = json.loads(_DATA.read_text(encoding='utf-8'))

GENRES_REPLACE: dict[str, list[str]] = _raw['replace']
GENRES_SKIP: list[str] = _raw['skip']
GENRES_PARTIAL_SKIP: list[str] = _raw['partial_skip']

REPLACE_LOOKUP: dict[str, str] = {}
for _canonical, _aliases in GENRES_REPLACE.items():
    REPLACE_LOOKUP[_canonical.lower()] = _canonical
    for _alias in _aliases:
        REPLACE_LOOKUP[_alias.lower()] = _canonical

SKIP_SET: set[str] = {s.lower() for s in GENRES_SKIP}
PARTIAL_SKIP: list[str] = [s.lower() for s in GENRES_PARTIAL_SKIP]
