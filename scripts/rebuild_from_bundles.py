from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phoenixadult.config.env import env
from phoenixadult.utils import db
from phoenixadult.utils.cache import BUNDLE_FILE, BUNDLE_ROOT, BUNDLE_VERSION, bundle_path, scene_store


def _read(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or int(payload.get('version') or 0) > BUNDLE_VERSION:
        return None
    if not all(payload.get(field) for field in ('site', 'cur_id', 'hash', 'response')):
        return None
    return payload


def restore(root: Path, overwrite: bool) -> dict[str, int]:
    stats = dict.fromkeys(('read', 'skipped', 'restored', 'unreadable'), 0)
    for path in sorted((root / BUNDLE_ROOT).rglob(BUNDLE_FILE)):
        payload = _read(path)
        if payload is None:
            stats['unreadable'] += 1
            print(f'  unreadable: {path.relative_to(root)}')
            continue
        stats['read'] += 1
        scene_hash = str(payload['hash'])
        if not overwrite and scene_store.has(scene_hash):
            stats['skipped'] += 1
            continue
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
        stats['restored'] += 1
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=f'Rebuild scene rows from the {BUNDLE_FILE} files in the snapshot cache.')
    parser.add_argument('--overwrite', action='store_true', help='replace rows that already exist (default: only fill in missing ones)')
    parser.add_argument('--cache-dir', default=None)
    args = parser.parse_args()

    root = Path(args.cache_dir or env.metadata_cache_dir)
    if not (root / BUNDLE_ROOT).exists():
        print(f'{root / BUNDLE_ROOT} does not exist')
        return 1
    stats = restore(root, args.overwrite)
    db.close()
    print(f'read {stats["read"]} bundle(s): restored {stats["restored"]}, skipped {stats["skipped"]} already present, {stats["unreadable"]} unreadable')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
