from __future__ import annotations

import json
import time
from typing import Any

from phoenixadult.utils import db

_KEEP_HEADERS = ('accept', 'accept-encoding', 'content-length', 'content-type', 'host', 'user-agent')


def record(client_id: str, headers: Any, path: str) -> None:
    kept = {k: v for k, v in headers.items() if k.lower() in _KEEP_HEADERS or k.lower().startswith('x-plex-')}
    now = time.time()
    conn = db.connect()
    with conn:
        conn.execute(
            'INSERT INTO client_hits (client_id, headers, count, first_seen, last_seen, last_path) VALUES (?, ?, 1, ?, ?, ?) '
            'ON CONFLICT(client_id) DO UPDATE SET headers = excluded.headers, count = client_hits.count + 1, '
            'last_seen = excluded.last_seen, last_path = excluded.last_path',
            (client_id, json.dumps(kept, sort_keys=True), now, now, path),
        )


def list_hits() -> list[dict[str, Any]]:
    rows = db.connect().execute('SELECT * FROM client_hits ORDER BY last_seen DESC').fetchall()
    return [
        {
            'clientId': r['client_id'],
            'headers': json.loads(r['headers'] or '{}'),
            'count': r['count'],
            'firstSeen': r['first_seen'],
            'lastSeen': r['last_seen'],
            'lastPath': r['last_path'],
        }
        for r in rows
    ]


def clear() -> None:
    conn = db.connect()
    with conn:
        conn.execute('DELETE FROM client_hits')
