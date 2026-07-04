from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, NamedTuple

_DATA = Path(__file__).parent / '_data' / 'json' / 'genres.json'
_STAT_INTERVAL = 5.0


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


_cache: tuple[float, GenreRules] | None = None
_stat_checked_at = 0.0
_reload_lock = threading.Lock()


def genre_rules() -> GenreRules:
    """Parsed genres.json, reloaded whenever the file's mtime changes — so edits to the
    skip / partial_skip / replace lists apply without a restart. The stat is
    rate-limited; it runs several times per scene."""
    global _cache, _stat_checked_at
    now = time.monotonic()
    if _cache is not None and now - _stat_checked_at < _STAT_INTERVAL:
        return _cache[1]
    _stat_checked_at = now
    try:
        mtime = _DATA.stat().st_mtime
    except OSError:
        mtime = 0.0
    if _cache is None or _cache[0] != mtime:
        with _reload_lock:
            if _cache is None or _cache[0] != mtime:
                _cache = (mtime, _build(json.loads(_DATA.read_text(encoding='utf-8'))))
    return _cache[1]
