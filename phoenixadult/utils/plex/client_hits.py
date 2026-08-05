from __future__ import annotations

import time
from typing import Any

from cachetools import LRUCache

_MAX_CLIENTS = 64
_KEEP_HEADERS = ('accept', 'accept-encoding', 'content-length', 'content-type', 'host', 'user-agent')

_hits: LRUCache[str, dict[str, Any]] = LRUCache(maxsize=_MAX_CLIENTS)


def record(client_id: str, headers: Any, path: str) -> None:
    kept = {k: v for k, v in headers.items() if k.lower() in _KEEP_HEADERS or k.lower().startswith('x-plex-')}
    now = time.time()
    entry = _hits.get(client_id)
    if entry is None:
        _hits[client_id] = {'clientId': client_id, 'headers': kept, 'count': 1, 'firstSeen': now, 'lastSeen': now, 'lastPath': path}
    else:
        entry.update({'headers': kept, 'count': entry['count'] + 1, 'lastSeen': now, 'lastPath': path})


def list_hits() -> list[dict[str, Any]]:
    return sorted(_hits.values(), key=lambda e: -float(e['lastSeen']))


def clear() -> None:
    _hits.clear()
