from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

from phoenixadult.config.env_catalog import is_editable_key
from phoenixadult.utils.fs.json_io import read_json

OVERRIDES_PATH = Path(os.environ.get('ENV_OVERRIDES_PATH') or (Path.cwd() / 'env.overrides.json'))

_overrides: dict[str, str] = {}
_baseline: dict[str, str | None] = {}
_lock = threading.Lock()


def _snapshot_baseline(key: str) -> None:
    if key not in _baseline:
        _baseline[key] = os.environ.get(key)


def _persist_locked() -> None:
    tmp = OVERRIDES_PATH.parent / f'{OVERRIDES_PATH.name}.tmp'
    try:
        tmp.write_text(json.dumps(_overrides, indent=2) + '\n', encoding='utf-8')
        os.replace(tmp, OVERRIDES_PATH)
    except OSError as err:
        logging.getLogger('phoenixadult').warning(f'[envOverrides] could not write {OVERRIDES_PATH}: {err}')


def load_overrides() -> None:
    if not OVERRIDES_PATH.exists():
        return
    raw = read_json(OVERRIDES_PATH, tag='envOverrides')
    if not isinstance(raw, dict):
        return
    with _lock:
        for key, value in raw.items():
            if not isinstance(value, str) or not is_editable_key(key):
                continue
            _snapshot_baseline(key)
            _overrides[key] = value
            os.environ[key] = value


def is_overridden(key: str) -> bool:
    return key in _overrides


def set_override(key: str, value: str) -> None:
    with _lock:
        _snapshot_baseline(key)
        _overrides[key] = value
        os.environ[key] = value
        _persist_locked()


def _restore_locked(key: str) -> None:
    del _overrides[key]
    if key in _baseline:
        original = _baseline[key]
        if original is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = original


def clear_override(key: str) -> None:
    with _lock:
        if key not in _overrides:
            return
        _restore_locked(key)
        _persist_locked()


def clear_all_overrides() -> None:
    with _lock:
        if not _overrides:
            return
        for key in list(_overrides):
            _restore_locked(key)
        _persist_locked()
