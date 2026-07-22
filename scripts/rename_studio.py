"""One-time metadata-cache migration for a studio rename: rewrites studio/tagline/
collection strings in snapshots and merges the old studio-slug folders into the new."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config.env import env
from app.utils.helpers.helpers import slugify


def _rewrite_file(path: Path, old: str, new: str) -> bool:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        entries = data['MediaContainer']['Metadata']
    except (OSError, ValueError, KeyError, TypeError):
        return False
    changed = False
    for md in entries:
        if not isinstance(md, dict):
            continue
        if md.get('studio') == old:
            md['studio'] = new
            changed = True
        if md.get('tagline') == old:
            md['tagline'] = new
            changed = True
        if md.get('tagline') and md.get('tagline') == md.get('studio'):
            md['tagline'] = None
            changed = True
        tags = [c.get('tag') for c in (md.get('Collection') or []) if isinstance(c, dict)]
        if old in tags:
            merged = list(dict.fromkeys(new if t == old else t for t in tags if t))
            md['Collection'] = [{'tag': t} for t in merged]
            changed = True
    if changed:
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    return changed


def _merge_dirs(root: Path, old_slug: str, new_slug: str) -> int:
    merged = 0
    for old_dir in sorted((p for p in root.rglob(old_slug) if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        target = old_dir.parent / new_slug
        target.mkdir(parents=True, exist_ok=True)
        for item in old_dir.iterdir():
            dest = target / item.name
            if dest.exists():
                if item.is_dir():
                    for sub in item.rglob('*'):
                        sub_dest = dest / sub.relative_to(item)
                        if sub.is_file() and not sub_dest.exists():
                            sub_dest.parent.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(sub), str(sub_dest))
                    shutil.rmtree(item, ignore_errors=True)
                continue
            shutil.move(str(item), str(dest))
        shutil.rmtree(old_dir, ignore_errors=True)
        merged += 1
    return merged


def migrate(root: Path, old: str, new: str) -> tuple[int, int]:
    files = sum(1 for p in root.rglob('*.json') if _rewrite_file(p, old, new))
    dirs = _merge_dirs(root, slugify(old), slugify(new))
    return files, dirs


def main() -> int:
    parser = argparse.ArgumentParser(description='Migrate the metadata cache after a studio rename.')
    parser.add_argument('old')
    parser.add_argument('new')
    parser.add_argument('--cache-dir', default=None)
    args = parser.parse_args()
    root = Path(args.cache_dir or env.metadata_cache_dir)
    if not root.is_dir():
        print(f'cache dir not found: {root}')
        return 1
    files, dirs = migrate(root, args.old, args.new)
    print(f'rewrote {files} snapshot(s), merged {dirs} folder(s); restart the server to refresh the cache index')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
