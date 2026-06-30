"""One-off migration: move flat people-cache images into role/gender subfolders.

The people cache used to be a flat directory of `<role>.<slug>[_gender].<ext>` files with a
single `.face_crop_log.json`. It is now organised into directors/ producers/ and
actors/<male|female|trans|unknown>/, each with its own crop log. This moves every existing
top-level file into its subfolder and splits the crop log accordingly. Idempotent — files
already nested are left alone. (Pre-existing crops have no preserved original; that's only
kept for images cached after the change.)

    python -m scripts.migrate_people_subfolders
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from app.utils.images.ext import IMAGE_EXTS
from app.utils.people.cache import _subdir_for, people_cache_dir
from app.utils.people.types import parse_person_filename

_LOG = '.face_crop_log.json'


def main() -> None:
    root = Path(people_cache_dir())
    if not root.exists():
        print(f'no people cache at {root}')
        return

    flat_log: dict[str, dict] = {}
    flat_log_path = root / _LOG
    if flat_log_path.exists():
        try:
            flat_log = {e.get('filename'): e for e in json.loads(flat_log_path.read_text(encoding='utf-8'))}
        except (OSError, ValueError):
            flat_log = {}

    per_subdir: dict[str, list[dict]] = {}
    moved = 0
    for f in sorted(root.iterdir()):  # top-level only; nested files are already migrated
        if not f.is_file() or f.name.startswith('.') or f.suffix.lower() not in IMAGE_EXTS:
            continue
        role, _, _ = parse_person_filename(f.name)
        if role not in ('actor', 'director', 'producer'):
            continue
        subdir = _subdir_for(f.name)
        dest = root / subdir / f.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(f), str(dest))
        moved += 1
        if f.name in flat_log:
            per_subdir.setdefault(subdir, []).append(flat_log[f.name])

    for subdir, entries in per_subdir.items():
        p = root / subdir / _LOG
        existing: list[dict] = []
        if p.exists():
            try:
                existing = json.loads(p.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                existing = []
        p.write_text(json.dumps(existing + entries, indent=2) + '\n', encoding='utf-8')

    if flat_log_path.exists():
        flat_log_path.unlink()
    print(f'migrated {moved} file(s) into subfolders; wrote {len(per_subdir)} per-folder crop log(s) under {root}')


if __name__ == '__main__':
    main()
