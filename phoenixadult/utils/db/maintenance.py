from __future__ import annotations

import shutil
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from phoenixadult.config.env import env
from phoenixadult.utils import db
from phoenixadult.utils.logging.logger import logger

_TAG = 'db-backup'
_PREFIX = 'phoenixadult-'


def _stamp() -> str:
    return datetime.now().strftime('%Y%m%d-%H%M%S')


def _backup_dir() -> Path:
    return Path(env.db_backup_dir) if env.db_backup_dir else Path(env.state_db_path).parent / 'backups'


def integrity_ok(path: Path) -> bool:
    try:
        conn = sqlite3.connect(str(path))
        try:
            row = conn.execute('PRAGMA quick_check').fetchone()
            return row is not None and str(row[0]) == 'ok'
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return False


def newest_valid_backup() -> Path | None:
    bdir = _backup_dir()
    if not bdir.is_dir():
        return None
    for backup in sorted(bdir.glob(f'{_PREFIX}*.db'), reverse=True):
        if integrity_ok(backup):
            return backup
    return None


def backup_age_hours() -> float:
    newest = newest_valid_backup()
    if newest is None:
        return float('inf')
    try:
        return max(0.0, (time.time() - newest.stat().st_mtime) / 3600)
    except OSError:
        return float('inf')


def backup_once() -> Path | None:
    src = Path(env.state_db_path)
    if not src.exists():
        return None
    bdir = _backup_dir()
    bdir.mkdir(parents=True, exist_ok=True)
    dest = bdir / f'{_PREFIX}{_stamp()}.db'
    db.connect().execute('VACUUM INTO ?', (str(dest),))
    keep = env.db_backup_keep
    for old in sorted(bdir.glob(f'{_PREFIX}*.db'))[:-keep]:
        old.unlink(missing_ok=True)
    logger.info(_TAG, f'backup written {dest.name}')
    return dest


def startup_recover_if_corrupt() -> None:
    path = Path(env.state_db_path)
    if not path.exists() or integrity_ok(path):
        return
    logger.error(_TAG, f'{path.name} failed its integrity check — attempting restore from backup')
    db.close()
    backup = newest_valid_backup()
    if backup is None:
        logger.error(_TAG, 'no valid backup to restore from — repair manually (sqlite3 .recover) or the store rebuilds by re-scraping')
        return
    quarantine = path.with_name(f'{path.name}.corrupt-{_stamp()}')
    try:
        path.rename(quarantine)
    except OSError as err:
        logger.error(_TAG, f'could not quarantine the corrupt db ({err!r}) — leaving it in place')
        return
    for suffix in ('-wal', '-shm'):
        path.with_name(path.name + suffix).unlink(missing_ok=True)
    shutil.copy2(backup, path)
    logger.warn(_TAG, f'restored {path.name} from {backup.name}; corrupt copy kept as {quarantine.name}')
