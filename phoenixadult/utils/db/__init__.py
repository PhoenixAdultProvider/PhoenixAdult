from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path

from phoenixadult.config.env import env
from phoenixadult.utils.logging.logger import logger

_BUSY_TIMEOUT_MS = 5000


def _backfill_image_sources(conn: sqlite3.Connection) -> None:
    from phoenixadult.utils.people.image_source import SCENE_SOURCE, source_for_url

    conn.execute("ALTER TABLE crop_log ADD COLUMN source TEXT NOT NULL DEFAULT ''")
    derived: list[tuple[str, str]] = []
    for row in conn.execute('SELECT rel_path, entry FROM crop_log').fetchall():
        try:
            entry = json.loads(str(row['entry']))
        except ValueError:
            continue
        url = str(entry.get('upstream_url') or '') if isinstance(entry, dict) else ''
        if url:
            derived.append((source_for_url(url) or SCENE_SOURCE, str(row['rel_path'])))
    conn.executemany('UPDATE crop_log SET source = ? WHERE rel_path = ?', derived)
    logger.info('db', f'derived the source of {len(derived)} cached headshot(s) from their URLs')


_Migration = str | Callable[[sqlite3.Connection], None]

_MIGRATIONS: list[_Migration] = [
    """
    CREATE TABLE queue_replays (
      key       TEXT PRIMARY KEY,
      replay    TEXT NOT NULL,
      queued_at REAL NOT NULL
    );
    CREATE TABLE searches (
      key_hash  TEXT PRIMARY KEY,
      site      TEXT NOT NULL,
      title     TEXT NOT NULL,
      date      TEXT NOT NULL,
      scene_id  TEXT NOT NULL,
      language  TEXT NOT NULL,
      saved_at  REAL NOT NULL
    );
    CREATE INDEX searches_similar ON searches(site, date, scene_id, language);
    CREATE INDEX searches_ttl ON searches(saved_at);
    CREATE TABLE search_results (
      key_hash TEXT NOT NULL REFERENCES searches(key_hash) ON DELETE CASCADE,
      pos      INTEGER NOT NULL,
      cur_id   TEXT NOT NULL,
      title    TEXT NOT NULL,
      subsite  TEXT NOT NULL DEFAULT '',
      payload  TEXT NOT NULL,
      PRIMARY KEY (key_hash, pos)
    );
    CREATE INDEX search_results_cur ON search_results(cur_id);
    """,
    """
    CREATE TABLE studios (
      id   INTEGER PRIMARY KEY,
      name TEXT NOT NULL UNIQUE
    );
    CREATE TABLE taglines (
      id   INTEGER PRIMARY KEY,
      name TEXT NOT NULL UNIQUE
    );
    CREATE TABLE genres (
      id   INTEGER PRIMARY KEY,
      name TEXT NOT NULL UNIQUE
    );
    CREATE TABLE collections (
      id   INTEGER PRIMARY KEY,
      name TEXT NOT NULL UNIQUE
    );
    CREATE TABLE countries (
      id   INTEGER PRIMARY KEY,
      name TEXT NOT NULL UNIQUE
    );
    CREATE TABLE scenes (
      id              INTEGER PRIMARY KEY,
      hash            TEXT NOT NULL UNIQUE,
      site            TEXT NOT NULL,
      cur_id          TEXT NOT NULL,
      rel_path        TEXT NOT NULL,
      identifier      TEXT NOT NULL,
      rating_key      TEXT NOT NULL,
      guid            TEXT NOT NULL,
      title           TEXT NOT NULL,
      title_sort      TEXT,
      original_title  TEXT,
      summary         TEXT,
      release_date    TEXT,
      year            INTEGER,
      duration        INTEGER,
      rating          REAL,
      audience_rating REAL,
      content_rating  TEXT,
      is_adult        INTEGER,
      data18_type     TEXT,
      data18_id       TEXT,
      thumb           TEXT,
      art             TEXT,
      studio_id       INTEGER REFERENCES studios(id),
      tagline_id      INTEGER REFERENCES taglines(id),
      updated_at      REAL NOT NULL
    );
    CREATE INDEX scenes_rel ON scenes(rel_path);
    CREATE INDEX scenes_updated ON scenes(updated_at);
    CREATE TABLE scene_genres (
      scene_id INTEGER NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
      genre_id INTEGER NOT NULL REFERENCES genres(id),
      pos      INTEGER NOT NULL,
      PRIMARY KEY (scene_id, genre_id)
    );
    CREATE TABLE scene_collections (
      scene_id      INTEGER NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
      collection_id INTEGER NOT NULL REFERENCES collections(id),
      pos           INTEGER NOT NULL,
      PRIMARY KEY (scene_id, collection_id)
    );
    CREATE TABLE scene_countries (
      scene_id   INTEGER NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
      country_id INTEGER NOT NULL REFERENCES countries(id),
      pos        INTEGER NOT NULL,
      PRIMARY KEY (scene_id, country_id)
    );
    CREATE TABLE people (
      id              INTEGER PRIMARY KEY,
      name            TEXT NOT NULL,
      scope_studio_id INTEGER REFERENCES studios(id),
      gender          TEXT NOT NULL DEFAULT '',
      iafd_id         TEXT,
      UNIQUE (name, scope_studio_id)
    );
    CREATE UNIQUE INDEX people_global ON people(name) WHERE scope_studio_id IS NULL;
    CREATE TABLE scene_people (
      scene_id       INTEGER NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
      person_id      INTEGER NOT NULL REFERENCES people(id),
      role           TEXT NOT NULL,
      part           TEXT,
      pos            INTEGER NOT NULL,
      photo_rel_path TEXT,
      PRIMARY KEY (scene_id, person_id, role)
    );
    CREATE TABLE scene_images (
      id       INTEGER PRIMARY KEY,
      scene_id INTEGER NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
      kind     TEXT NOT NULL,
      rel_path TEXT NOT NULL,
      width    INTEGER,
      height   INTEGER,
      bytes    INTEGER,
      pos      INTEGER NOT NULL
    );
    CREATE INDEX scene_images_scene ON scene_images(scene_id);
    """,
    """
    CREATE TABLE people_images (
      type     TEXT NOT NULL,
      slug     TEXT NOT NULL,
      gender   TEXT NOT NULL DEFAULT '',
      ext      TEXT NOT NULL,
      rel_path TEXT NOT NULL,
      mtime    REAL NOT NULL,
      PRIMARY KEY (type, slug, gender)
    );
    CREATE TABLE logos (
      studio_slug TEXT NOT NULL DEFAULT '',
      name_slug   TEXT NOT NULL,
      rel_path    TEXT NOT NULL,
      mtime       REAL NOT NULL,
      PRIMARY KEY (studio_slug, name_slug)
    );
    CREATE INDEX logos_name ON logos(name_slug);
    CREATE TABLE crop_log (
      rel_path   TEXT PRIMARY KEY,
      entry      TEXT NOT NULL,
      cropped_at REAL NOT NULL
    );
    """,
    """
    ALTER TABLE scenes ADD COLUMN force_refresh INTEGER NOT NULL DEFAULT 0;
    CREATE INDEX scenes_force ON scenes(force_refresh) WHERE force_refresh = 1;
    """,
    _backfill_image_sources,
    """
    ALTER TABLE scenes ADD COLUMN data18_manual INTEGER NOT NULL DEFAULT 0;
    """,
]

_local = threading.local()
_open: list[sqlite3.Connection] = []
_lock = threading.Lock()
_current: tuple[str, int] = ('', 0)
_migrated = False


def _discard() -> None:
    global _current, _migrated
    for conn in _open:
        conn.close()
    _open.clear()
    _migrated = False
    _current = (_current[0], _current[1] + 1)


def _epoch() -> tuple[str, int]:
    global _current
    path = str(Path(env.state_db_path))
    with _lock:
        if _current[0] != path:
            _discard()
            _current = (path, _current[1])
        return _current


def connect() -> sqlite3.Connection:
    """This thread's connection (WAL, FK-enforced, migrated) — one handle is not safe to share
    across the to_thread workers. Opening is serialized: a fresh database's WAL switch needs a lock."""
    global _migrated
    key = _epoch()
    cached: sqlite3.Connection | None = getattr(_local, 'conn', None)
    if cached is not None and getattr(_local, 'key', None) == key:
        return cached
    Path(key[0]).parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        conn = sqlite3.connect(key[0], check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute(f'PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}')
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
        conn.execute('PRAGMA foreign_keys=ON')
        if not _migrated:
            _migrate(conn)
            _migrated = True
        _open.append(conn)
    _local.conn, _local.key = conn, key
    return conn


def close() -> None:
    with _lock:
        _discard()


def _migrate(conn: sqlite3.Connection) -> None:
    version = int(conn.execute('PRAGMA user_version').fetchone()[0])
    for idx, step in enumerate(_MIGRATIONS[version:], start=version + 1):
        if isinstance(step, str):
            conn.executescript(step)
        else:
            step(conn)
        conn.execute(f'PRAGMA user_version = {idx}')
        conn.commit()
        logger.info('db', f'phoenixadult.db schema migrated to v{idx}')


# ── Shared Helpers ────────────────────────────────────────────────────────────


class ReconciledConn:
    """Rebuild gate for tables mirroring an on-disk directory: when (dir, phoenixadult.db path)
    changes, the rebuild callback runs once before the shared connection is handed back."""

    def __init__(self, dir_of: Callable[[], str], rebuild: Callable[[], object]) -> None:
        self._dir_of = dir_of
        self._rebuild = rebuild
        self._key: tuple[str, str] | None = None
        self._lock = threading.Lock()

    def invalidate(self) -> None:
        with self._lock:
            self._key = None

    def reconcile(self) -> None:
        with self._lock:
            self._rebuild_locked()

    def _rebuild_locked(self) -> None:
        """The key is stored only after a successful rebuild: a reader that arrives mid-rebuild
        waits on the lock rather than seeing the half-emptied table, and a failed rebuild retries."""
        key = (self._dir_of(), env.state_db_path)
        self._rebuild()
        self._key = key

    def connect(self) -> sqlite3.Connection:
        if self._key != (self._dir_of(), env.state_db_path):
            with self._lock:
                if self._key != (self._dir_of(), env.state_db_path):
                    self._rebuild_locked()
        return connect()


def like_escape(value: str) -> str:
    """Escape LIKE wildcards for a pattern used with ESCAPE '\\'."""
    return value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def like_contains(value: str) -> str:
    return f'%{like_escape(value)}%'


def like_prefix(value: str) -> str:
    return f'{like_escape(value)}%'


def dim_id(conn: sqlite3.Connection, table: str, name: str, unique_col: str = 'name') -> int | None:
    """INSERT OR IGNORE + id lookup for a unique dimension row; None for a blank value."""
    if not name:
        return None
    conn.execute(f'INSERT OR IGNORE INTO {table}({unique_col}) VALUES(?)', (name,))
    return int(conn.execute(f'SELECT id FROM {table} WHERE {unique_col} = ?', (name,)).fetchone()['id'])
