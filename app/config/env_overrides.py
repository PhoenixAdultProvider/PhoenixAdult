from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from app.config.env_catalog import is_editable_key

OVERRIDES_PATH = Path(os.environ.get('ENV_OVERRIDES_PATH') or (Path.cwd() / 'env.overrides.json'))

_overrides: dict[str, str] = {}
_baseline: dict[str, str | None] = {}
_persist_lock = threading.Lock()


def _snapshot_baseline(key: str) -> None:
    if key not in _baseline:
        _baseline[key] = os.environ.get(key)


def _persist() -> None:
    # tmp + replace: a crash mid-write must never truncate the overrides file.
    tmp = OVERRIDES_PATH.parent / f'{OVERRIDES_PATH.name}.tmp'
    with _persist_lock:
        try:
            tmp.write_text(json.dumps(_overrides, indent=2) + '\n', encoding='utf-8')
            os.replace(tmp, OVERRIDES_PATH)
        except OSError as err:
            print(f'[envOverrides] could not write {OVERRIDES_PATH}: {err}')


def load_overrides() -> None:
    if not OVERRIDES_PATH.exists():
        return
    try:
        raw = json.loads(OVERRIDES_PATH.read_text(encoding='utf-8'))
    except (OSError, ValueError) as err:
        print(f'[envOverrides] could not read {OVERRIDES_PATH}: {err}')
        return
    if not isinstance(raw, dict):
        return
    for key, value in raw.items():
        if not isinstance(value, str) or not is_editable_key(key):
            continue
        _snapshot_baseline(key)
        _overrides[key] = value
        os.environ[key] = value


def is_overridden(key: str) -> bool:
    return key in _overrides


def set_override(key: str, value: str) -> None:
    _snapshot_baseline(key)
    _overrides[key] = value
    os.environ[key] = value
    _persist()


def clear_override(key: str) -> None:
    if key not in _overrides:
        return
    del _overrides[key]
    if key in _baseline:
        original = _baseline[key]
        if original is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = original
    _persist()


def clear_all_overrides() -> None:
    for key in list(_overrides.keys()):
        clear_override(key)
