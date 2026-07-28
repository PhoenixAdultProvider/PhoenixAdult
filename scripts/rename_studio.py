from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phoenixadult.utils import db


def _rename_dimension(table: str, old: str, new: str) -> int:
    conn = db.connect()
    old_row = conn.execute(f'SELECT id FROM {table} WHERE name = ? COLLATE NOCASE', (old,)).fetchone()  # noqa: S608 - fixed table names
    if old_row is None:
        return 0
    new_row = conn.execute(f'SELECT id FROM {table} WHERE name = ? COLLATE NOCASE', (new,)).fetchone()  # noqa: S608
    with conn:
        if new_row is None or int(new_row['id']) == int(old_row['id']):
            conn.execute(f'UPDATE {table} SET name = ? WHERE id = ?', (new, old_row['id']))  # noqa: S608
        else:
            db.merge_name_row(conn, table, int(new_row['id']), int(old_row['id']))
    return 1


def migrate(old: str, new: str, tables: list[str] | None = None) -> int:
    return sum(_rename_dimension(t, old, new) for t in (tables or list(db.NAME_DIMENSIONS)))


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Rename or recase a studio, tagline, collection, genre or person in phoenixadult.db. '
        'Matching ignores capitalisation, so this is also how you change the casing of a stored name. '
        'Snapshot folders are keyed by scene hash and never move.'
    )
    parser.add_argument('old')
    parser.add_argument('new')
    parser.add_argument('--table', action='append', choices=sorted(db.NAME_DIMENSIONS), help='limit to one table (repeatable; default: all)')
    args = parser.parse_args()
    dims = migrate(args.old, args.new, args.table)
    print(f'renamed {dims} dimension row(s); restart the server')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
