from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.utils.logging.logger import logger

_FILE = '.face_crop_log.json'
_MAX = 20


def _path(directory: str) -> Path:
    return Path(directory) / _FILE


def _load(directory: str) -> list[dict[str, Any]]:
    p = _path(directory)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
        return data if isinstance(data, list) else []
    except (ValueError, OSError):
        return []


def _save(directory: str, entries: list[dict[str, Any]]) -> None:
    try:
        _path(directory).write_text(json.dumps(entries[-_MAX:], indent=2), encoding='utf-8')
    except OSError as err:
        logger.warn('face-crop', f'could not write crop log: {err}')


def record(directory: str, *, name: str, filename: str, base: str, orig_ext: str, upstream_url: str, cropped: bool) -> None:
    entries = [e for e in _load(directory) if e.get('filename') != filename]
    entries.append(
        {
            'name': name,
            'filename': filename,
            'base': base,
            'orig_ext': orig_ext,
            'upstream_url': upstream_url,
            'cropped': cropped,
            'ts': datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S'),
        }
    )
    _save(directory, entries)


def recent(directory: str) -> list[dict[str, Any]]:
    return list(reversed(_load(directory)))  # newest first


def remove(directory: str, filename: str) -> None:
    entries = [e for e in _load(directory) if e.get('filename') != filename]
    _save(directory, entries)


def update(directory: str, match_filename: str, **changes: Any) -> None:
    entries = _load(directory)
    for e in entries:
        if e.get('filename') == match_filename:
            e.update(changes)
            break
    _save(directory, entries)
