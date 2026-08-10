from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phoenixadult.utils.cache import BUNDLE_FILE, BUNDLE_ROOT, BUNDLE_VERSION, bundle_path, cache_dir, enabled, scene_store
from phoenixadult.utils.logging.logger import logger


def read_bundle(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or int(payload.get('version') or 0) > BUNDLE_VERSION:
        return None
    if not all(payload.get(field) for field in ('site', 'cur_id', 'hash', 'response')):
        return None
    return payload


def _register(path: Path, payload: dict[str, Any]) -> None:
    scene_hash = str(payload['hash'])
    dims = {url: (int(v[0]), int(v[1]), int(v[2])) for url, v in (payload.get('images') or {}).items() if len(v) == 3}
    scene_store.upsert(
        str(payload['site']),
        str(payload['cur_id']),
        scene_hash,
        bundle_path(scene_hash),
        payload['response'],
        dims,
        updated_at=path.stat().st_mtime,
    )


def sweep(root: Path, overwrite: bool = False) -> dict[str, int]:
    stats = dict.fromkeys(('adopted', 'skipped', 'unreadable'), 0)
    known = scene_store.known_hashes()
    for path in sorted((root / BUNDLE_ROOT).rglob(BUNDLE_FILE)):
        if not overwrite and path.parent.name in known:
            stats['skipped'] += 1
            continue
        payload = read_bundle(path)
        if payload is None:
            stats['unreadable'] += 1
            logger.warn('meta-cache', f'unreadable bundle: {path}')
            continue
        _register(path, payload)
        stats['adopted'] += 1
    return stats


def startup_sweep() -> None:
    if not enabled():
        return
    root = Path(cache_dir())
    if not (root / BUNDLE_ROOT).exists():
        return
    stats = sweep(root)
    if stats['adopted'] or stats['unreadable']:
        logger.info('meta-cache', f'bundle sweep adopted {stats["adopted"]} snapshot(s) found on disk ({stats["unreadable"]} unreadable)')
