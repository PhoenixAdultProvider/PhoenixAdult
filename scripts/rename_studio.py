from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phoenixadult.utils import db


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


def migrate(old: str, new: str) -> int:
    return sum(_rename_dimension(t, old, new) for t in ('studios', 'taglines', 'collections'))


def main() -> int:
    parser = argparse.ArgumentParser(description='Rename a studio/tagline in phoenixadult.db. Snapshot folders are keyed by scene hash and never move.')
    parser.add_argument('old')
    parser.add_argument('new')
    args = parser.parse_args()
    dims = migrate(args.old, args.new)
    print(f'renamed {dims} dimension row(s); restart the server')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
