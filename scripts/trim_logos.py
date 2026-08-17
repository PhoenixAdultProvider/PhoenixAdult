from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

from phoenixadult.utils.images import logo_cache, logo_trim


def _candidates(root: Path) -> list[Path]:
    return sorted(f for f in root.rglob('*') if f.is_file() and f.suffix.lower() in logo_cache._RASTER_EXTS)


def main() -> int:
    parser = argparse.ArgumentParser(description='Trim dead space from cached logos')
    parser.add_argument('--apply', action='store_true', help='rewrite the files (default is a dry run)')
    parser.add_argument('--min-waste', type=float, default=1.0, help='only report/trim logos wasting at least this percent of area')
    args = parser.parse_args()

    root = logo_cache.cache_dir()
    if not root.exists():
        print(f'no logo cache at {root}')
        return 1

    files = _candidates(root)
    print(f'{len(files)} logos in {root}\n')
    hits: list[tuple[Path, tuple[int, int], tuple[int, int], float]] = []
    for f in files:
        try:
            with Image.open(f) as im:
                im.load()
                before = im.size
                box = logo_trim.content_box(im)
        except (OSError, ValueError):
            continue
        if box is None or box == (0, 0, *before):
            continue
        after = (box[2] - box[0], box[3] - box[1])
        if min(after) < logo_trim.MIN_SIDE:
            continue
        waste = 100 * (1 - (after[0] * after[1]) / (before[0] * before[1]))
        if waste >= args.min_waste:
            hits.append((f, before, after, waste))

    hits.sort(key=lambda h: -h[3])
    for f, before, after, waste in hits:
        rel = f.relative_to(root)
        print(f'{waste:5.1f}%  {before[0]}x{before[1]} -> {after[0]}x{after[1]}  {rel}')

    if not hits:
        print('nothing to trim')
        return 0

    total = sum(h[3] for h in hits) / len(hits)
    print(f'\n{len(hits)} logos with dead space, {total:.1f}% average waste')
    if not args.apply:
        print('dry run — re-run with --apply to rewrite these files')
        return 0

    trimmed = 0
    for f, _, _, _ in hits:
        if logo_trim.trim(f) is not None:
            trimmed += 1
    print(f'trimmed {trimmed} logos')
    try:
        logo_cache.invalidate()
        logo_cache.reconcile()
    except (OSError, RuntimeError, sqlite3.Error) as exc:
        print(f'index not rebuilt ({exc}); the files are trimmed — use Rescan Folder on /logos')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
