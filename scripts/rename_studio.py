"""Studio/tagline rename tool: one dimension UPDATE in state.db, image-folder merge to
the new slug, and rel_path fixups so DB rows keep pointing at the moved files."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config.env import env
from app.utils import db
from app.utils.helpers.helpers import slugify


def _rename_dimension(table: str, old: str, new: str) -> int:
    conn = db.connect()
    old_row = conn.execute(f'SELECT id FROM {table} WHERE name = ?', (old,)).fetchone()  # noqa: S608 - fixed table names
    if old_row is None:
        return 0
    new_row = conn.execute(f'SELECT id FROM {table} WHERE name = ?', (new,)).fetchone()  # noqa: S608
    with conn:
        if new_row is None:
            conn.execute(f'UPDATE {table} SET name = ? WHERE id = ?', (new, old_row['id']))  # noqa: S608
            return 1
        old_id, new_id = old_row['id'], new_row['id']
        if table == 'studios':
            conn.execute('UPDATE scenes SET studio_id = ? WHERE studio_id = ?', (new_id, old_id))
            conn.execute('UPDATE OR IGNORE people SET scope_studio_id = ? WHERE scope_studio_id = ?', (new_id, old_id))
        if table == 'taglines':
            conn.execute('UPDATE scenes SET tagline_id = ? WHERE tagline_id = ?', (new_id, old_id))
        if table == 'collections':
            conn.execute('UPDATE OR IGNORE scene_collections SET collection_id = ? WHERE collection_id = ?', (new_id, old_id))
            conn.execute('DELETE FROM scene_collections WHERE collection_id = ?', (old_id,))
        conn.execute(f'DELETE FROM {table} WHERE id = ?', (old_id,))  # noqa: S608
    return 1


def _fix_rel_paths(old_slug: str, new_slug: str) -> int:
    conn = db.connect()
    fixed = 0
    for table, column in (('scenes', 'rel_path'), ('scene_images', 'rel_path')):
        for row in conn.execute(f'SELECT rowid AS rid, {column} AS p FROM {table}').fetchall():  # noqa: S608
            parts = str(row['p']).split('/')
            if old_slug not in parts:
                continue
            new_path = '/'.join(new_slug if seg == old_slug else seg for seg in parts)
            with conn:
                conn.execute(f'UPDATE {table} SET {column} = ? WHERE rowid = ?', (new_path, row['rid']))  # noqa: S608
            fixed += 1
    return fixed


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


def migrate(root: Path, old: str, new: str) -> tuple[int, int, int]:
    dims = sum(_rename_dimension(t, old, new) for t in ('studios', 'taglines', 'collections'))
    dirs = _merge_dirs(root, slugify(old), slugify(new))
    paths = _fix_rel_paths(slugify(old), slugify(new))
    return dims, dirs, paths


def main() -> int:
    parser = argparse.ArgumentParser(description='Rename a studio/tagline across state.db and the image cache.')
    parser.add_argument('old')
    parser.add_argument('new')
    parser.add_argument('--cache-dir', default=None)
    args = parser.parse_args()
    root = Path(args.cache_dir or env.metadata_cache_dir)
    dims, dirs, paths = migrate(root, args.old, args.new)
    print(f'renamed {dims} dimension row(s), merged {dirs} folder(s), fixed {paths} rel_path(s); restart the server')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
