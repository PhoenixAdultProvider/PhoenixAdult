from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phoenixadult.config.env import env
from phoenixadult.utils import db
from phoenixadult.utils.cache import scene_store
from phoenixadult.utils.cache.layout import BUNDLE_FILE, BUNDLE_ROOT, bundle_path, bundle_payload

_STAGING = '_plex-import'
_ROOTS = {BUNDLE_ROOT, _STAGING}


def _move(src: Path, dst: Path) -> str:
    if dst.exists():
        shutil.rmtree(src, ignore_errors=True)
        return 'replaced'
    if not src.exists():
        return 'rowonly'
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return 'moved'


def _write_bundle(root: Path, scene: dict[str, str]) -> bool:
    loaded = scene_store.load(scene['hash'])
    if loaded is None:
        return False
    target = root / scene['rel_path']
    target.mkdir(parents=True, exist_ok=True)
    payload = bundle_payload(scene['site'], scene['cur_id'], scene['hash'], loaded, scene_store.image_dims(scene['hash']))
    (target / BUNDLE_FILE).write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    return True


def _prune_empty(root: Path) -> int:
    removed = 0
    for path in sorted((p for p in root.rglob('*') if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if path.parent == root and path.name in _ROOTS:
            continue
        if any(path.iterdir()):
            continue
        path.rmdir()
        removed += 1
    return removed


def orphans(root: Path) -> list[Path]:
    if not root.exists():
        return []
    known = {root / scene['rel_path'] for scene in scene_store.all_scenes()}
    found = set()
    for images in root.rglob('images'):
        snapshot = images.parent
        if images.is_dir() and snapshot not in known and snapshot.relative_to(root).parts[0] != _STAGING:
            found.add(snapshot)
    return sorted(found)


def migrate(root: Path, apply: bool, prune: bool) -> dict[str, int]:
    stats = dict.fromkeys(('moved', 'rowonly', 'replaced', 'bundled', 'orphans', 'pruned', 'stale_rows'), 0)
    stats['stale_rows'] = scene_store.orphan_image_count()
    for scene in scene_store.legacy_scenes(f'{BUNDLE_ROOT}/%'):
        rel = bundle_path(scene['hash'])
        if not apply:
            print(f'  {scene["rel_path"]} -> {rel}')
            stats['moved'] += 1
            continue
        stats[_move(root / scene['rel_path'], root / rel)] += 1
        scene_store.relocate(scene['hash'], rel)

    if apply:
        for scene in scene_store.all_scenes():
            stats['bundled'] += int(_write_bundle(root, scene))
        stats['pruned'] += _prune_empty(root)

    stale = orphans(root)
    stats['orphans'] = len(stale)
    for path in stale:
        print(f'  orphan: {path.relative_to(root)}')
        if apply and prune:
            shutil.rmtree(path, ignore_errors=True)
            stats['pruned'] += 1
    if apply and prune:
        if stale:
            stats['pruned'] += _prune_empty(root)
        stats['stale_rows'] = scene_store.drop_orphan_images()
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=f'Move snapshot folders to the {BUNDLE_ROOT}/<xx>/<hash> layout and write per-scene bundles.')
    parser.add_argument('--apply', action='store_true', help='perform the migration (default: report only)')
    parser.add_argument('--prune-orphans', action='store_true', help='also delete snapshot folders no scene row points at')
    parser.add_argument('--cache-dir', default=None)
    args = parser.parse_args()

    root = Path(args.cache_dir or env.metadata_cache_dir)
    if not root.exists():
        print(f'{root} does not exist')
        return 1
    pending = scene_store.legacy_count(f'{BUNDLE_ROOT}/%')
    total = len(scene_store.all_scenes())
    suffix = '' if args.apply else ' — dry run, pass --apply to migrate'
    print(f'{root}: {total} snapshot(s), {pending} on the old layout{suffix}')

    stats = migrate(root, args.apply, args.prune_orphans)
    db.close()
    if not args.apply:
        print(f'\nwould move {stats["moved"]} folder(s); {stats["orphans"]} orphan folder(s) and {stats["stale_rows"]} stale image row(s) found')
        return 0
    print(
        f'\nmoved {stats["moved"]}, replaced {stats["replaced"]}, rewrote {stats["rowonly"]} row(s) with no folder, '
        f'wrote {stats["bundled"]} bundle(s), pruned {stats["pruned"]} folder(s) of {stats["orphans"]} orphan(s), '
        f'dropped {stats["stale_rows"]} stale image row(s); restart the server'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
