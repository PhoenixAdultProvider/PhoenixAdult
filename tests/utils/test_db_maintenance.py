from __future__ import annotations

from pathlib import Path

import pytest

from phoenixadult.utils import db
from phoenixadult.utils.db import maintenance


@pytest.fixture(autouse=True)
def _db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv('STATE_DB_PATH', str(tmp_path / 'phoenixadult.db'))
    monkeypatch.setenv('DB_BACKUP_DIR', str(tmp_path / 'backups'))
    yield tmp_path
    db.close()


def _row_count() -> int:
    return int(db.connect().execute('SELECT COUNT(*) c FROM queue_replays').fetchone()['c'])


def test_backup_snapshots_and_prunes(monkeypatch: pytest.MonkeyPatch, _db: Path) -> None:
    monkeypatch.setenv('DB_BACKUP_KEEP', '2')
    db.connect().execute("INSERT INTO queue_replays(key, replay, queued_at) VALUES('k', '{}', 0)")
    db.connect().commit()

    stamps = iter(['20260101-000000', '20260102-000000', '20260103-000000'])
    monkeypatch.setattr(maintenance, '_stamp', lambda: next(stamps))
    made = [maintenance.backup_once() for _ in range(3)]
    assert all(p is not None for p in made)
    kept = sorted((_db / 'backups').glob('phoenixadult-*.db'))
    assert len(kept) == 2
    assert maintenance.integrity_ok(kept[-1])
    import sqlite3

    conn = sqlite3.connect(str(kept[-1]))
    assert conn.execute('SELECT COUNT(*) FROM queue_replays').fetchone()[0] == 1
    conn.close()


def test_integrity_ok_flags_a_garbage_file(_db: Path) -> None:
    bad = _db / 'bad.db'
    bad.write_bytes(b'this is not a sqlite database' * 100)
    assert maintenance.integrity_ok(bad) is False


def test_startup_restores_from_backup_when_corrupt(_db: Path) -> None:
    db.connect().execute("INSERT INTO queue_replays(key, replay, queued_at) VALUES('good', '{}', 0)")
    db.connect().commit()
    maintenance.backup_once()
    db.close()

    live = Path(maintenance.env.state_db_path)
    for suffix in ('', '-wal', '-shm'):
        Path(str(live) + suffix).unlink(missing_ok=True)
    live.write_bytes(b'corrupt garbage' * 500)

    maintenance.startup_recover_if_corrupt()

    assert maintenance.integrity_ok(live)
    assert _row_count() == 1
    assert list(_db.glob('phoenixadult.db.corrupt-*'))


def test_startup_leaves_corrupt_db_when_no_backup(_db: Path) -> None:
    db.connect().execute("INSERT INTO queue_replays(key, replay, queued_at) VALUES('x', '{}', 0)")
    db.connect().commit()
    db.close()
    live = Path(maintenance.env.state_db_path)
    for suffix in ('-wal', '-shm'):
        Path(str(live) + suffix).unlink(missing_ok=True)
    live.write_bytes(b'corrupt garbage' * 500)

    maintenance.startup_recover_if_corrupt()

    assert live.exists() and not list(_db.glob('phoenixadult.db.corrupt-*'))


def test_backup_age_reports_infinity_when_none_exists() -> None:
    assert maintenance.backup_age_hours() == float('inf')


def test_backup_age_tracks_the_newest_backup(monkeypatch: pytest.MonkeyPatch) -> None:
    import os
    import time

    db.connect()
    made = maintenance.backup_once()
    assert made is not None
    assert maintenance.backup_age_hours() < 1

    stale = time.time() - 48 * 3600
    os.utime(made, (stale, stale))
    assert maintenance.backup_age_hours() > 47
