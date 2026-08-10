from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phoenixadult.config.env import env
from phoenixadult.utils import db
from phoenixadult.utils.cache import BUNDLE_FILE, BUNDLE_ROOT, bundle_sweep


def main() -> int:
    parser = argparse.ArgumentParser(description=f'Rebuild scene rows from the {BUNDLE_FILE} files in the snapshot cache.')
    parser.add_argument('--overwrite', action='store_true', help='replace rows that already exist (default: only fill in missing ones)')
    parser.add_argument('--cache-dir', default=None)
    args = parser.parse_args()

    root = Path(args.cache_dir or env.metadata_cache_dir)
    if not (root / BUNDLE_ROOT).exists():
        print(f'{root / BUNDLE_ROOT} does not exist')
        return 1
    stats = bundle_sweep.sweep(root, args.overwrite)
    db.close()
    print(f'adopted {stats["adopted"]} bundle(s), skipped {stats["skipped"]} already present, {stats["unreadable"]} unreadable')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
