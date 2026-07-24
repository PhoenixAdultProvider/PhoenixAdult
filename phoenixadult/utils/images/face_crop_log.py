from __future__ import annotations

import json
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from phoenixadult.config.env import env
from phoenixadult.utils import db
from phoenixadult.utils.fs.paths import rel_to


def _root() -> Path:
    return Path(env.people_cache_dir)


def _rel_dir(directory: str) -> str:
    return rel_to(directory, _root()) or Path(directory).as_posix()


def _conn() -> sqlite3.Connection:
    return db.connect()


def record(directory: str, *, name: str, filename: str, base: str, orig_ext: str, upstream_url: str, cropped: bool) -> None:
    entry = {
        'name': name,
        'filename': filename,
        'base': base,
        'orig_ext': orig_ext,
        'upstream_url': upstream_url,
        'cropped': cropped,
        'ts': datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S'),
    }
    conn = _conn()
    with conn:
        conn.execute(
            'INSERT OR REPLACE INTO crop_log(rel_path, entry, cropped_at) VALUES(?, ?, ?)',
            (f'{_rel_dir(directory)}/{filename}', json.dumps(entry), time.time()),
        )


def _parse_entry(raw: str) -> dict[str, Any] | None:
    try:
        entry = json.loads(raw)
    except ValueError:
        return None
    return entry if isinstance(entry, dict) else None


def recent(directory: str) -> list[dict[str, Any]]:
    rel_dir = _rel_dir(directory)
    rows = (
        _conn()
        .execute("SELECT rel_path, entry FROM crop_log WHERE rel_path LIKE ? ESCAPE '\\' ORDER BY cropped_at DESC, rel_path", (db.like_prefix(f'{rel_dir}/'),))
        .fetchall()
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        if str(row['rel_path']).rpartition('/')[0] != rel_dir:
            continue
        entry = _parse_entry(str(row['entry']))
        if entry is not None:
            out.append(entry)
    return out


def entry_for(directory: str, filename: str) -> dict[str, Any] | None:
    """The single crop-log entry keyed by directory/filename, None when absent."""
    row = _conn().execute('SELECT entry FROM crop_log WHERE rel_path = ?', (f'{_rel_dir(directory)}/{filename}',)).fetchone()
    return None if row is None else _parse_entry(str(row['entry']))


def entries_by_path() -> dict[str, dict[str, Any]]:
    """All crop-log entries keyed by their root-relative path."""
    out: dict[str, dict[str, Any]] = {}
    for row in _conn().execute('SELECT rel_path, entry FROM crop_log').fetchall():
        entry = _parse_entry(str(row['entry']))
        if entry is not None:
            out[str(row['rel_path'])] = entry
    return out


def remove(directory: str, filename: str) -> None:
    conn = _conn()
    with conn:
        conn.execute('DELETE FROM crop_log WHERE rel_path = ?', (f'{_rel_dir(directory)}/{filename}',))


def update(directory: str, match_filename: str, **changes: Any) -> None:
    rel_dir = _rel_dir(directory)
    key = f'{rel_dir}/{match_filename}'
    conn = _conn()
    with conn:
        row = conn.execute('SELECT entry, cropped_at FROM crop_log WHERE rel_path = ?', (key,)).fetchone()
        if row is None:
            return
        try:
            entry = json.loads(row['entry'])
        except ValueError:
            return
        if not isinstance(entry, dict):
            return
        entry.update(changes)
        new_key = f'{rel_dir}/{entry.get("filename") or match_filename}'
        if new_key != key:
            conn.execute('DELETE FROM crop_log WHERE rel_path = ?', (key,))
        conn.execute('INSERT OR REPLACE INTO crop_log(rel_path, entry, cropped_at) VALUES(?, ?, ?)', (new_key, json.dumps(entry), float(row['cropped_at'])))
