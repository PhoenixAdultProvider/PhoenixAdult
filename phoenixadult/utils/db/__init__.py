from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from phoenixadult.config.env import env
from phoenixadult.utils.logging.logger import logger

_BUSY_TIMEOUT_MS = 5000


@dataclass(frozen=True)
class NameDimension:
    junctions: tuple[tuple[str, str], ...] = ()
    refs: tuple[tuple[str, str], ...] = ()


NAME_DIMENSIONS: dict[str, NameDimension] = {
    'people': NameDimension(junctions=(('scene_people', 'person_id'),)),
    'studios': NameDimension(refs=(('scenes', 'studio_id'), ('people', 'scope_studio_id'))),
    'taglines': NameDimension(refs=(('scenes', 'tagline_id'),)),
    'collections': NameDimension(junctions=(('scene_collections', 'collection_id'),)),
    'genres': NameDimension(junctions=(('scene_genres', 'genre_id'),)),
    'countries': NameDimension(junctions=(('scene_countries', 'country_id'),)),
}


def merge_name_row(conn: sqlite3.Connection, table: str, keep: int, drop: int) -> None:
    spec = NAME_DIMENSIONS[table]
    for child, column in spec.junctions:
        conn.execute(f'UPDATE OR IGNORE {child} SET {column} = ? WHERE {column} = ?', (keep, drop))  # noqa: S608 - fixed table names
        conn.execute(f'DELETE FROM {child} WHERE {column} = ?', (drop,))  # noqa: S608
    for child, column in spec.refs:
        conn.execute(f'UPDATE {child} SET {column} = ? WHERE {column} = ?', (keep, drop))  # noqa: S608
    conn.execute(f'DELETE FROM {table} WHERE id = ?', (drop,))  # noqa: S608


def prune_orphan_names(conn: sqlite3.Connection) -> dict[str, int]:
    pruned: dict[str, int] = {}
    for table, spec in NAME_DIMENSIONS.items():
        clauses = ' AND '.join(f'NOT EXISTS (SELECT 1 FROM {child} WHERE {child}.{column} = {table}.id)' for child, column in (*spec.junctions, *spec.refs))
        cursor = conn.execute(f'DELETE FROM {table} WHERE {clauses}')  # noqa: S608 - fixed table names
        if cursor.rowcount:
            pruned[table] = cursor.rowcount
    if pruned:
        logger.info('db', 'pruned unreferenced names: ' + ', '.join(f'{n} {table}' for table, n in pruned.items()))
    return pruned


_SCHEMA_V1 = """
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
        , force_refresh INTEGER NOT NULL DEFAULT 0, data18_manual INTEGER NOT NULL DEFAULT 0, data18_also TEXT NOT NULL DEFAULT '');
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
        , priority INTEGER NOT NULL DEFAULT 0);
    CREATE INDEX scene_images_scene ON scene_images(scene_id);
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
        , source TEXT NOT NULL DEFAULT '');
    CREATE INDEX scenes_force ON scenes(force_refresh) WHERE force_refresh = 1;
    CREATE UNIQUE INDEX people_ci_global ON people(name COLLATE NOCASE) WHERE scope_studio_id IS NULL;
    CREATE UNIQUE INDEX people_ci_scoped ON people(name COLLATE NOCASE, scope_studio_id) WHERE scope_studio_id IS NOT NULL;
    CREATE UNIQUE INDEX studios_ci ON studios(name COLLATE NOCASE);
    CREATE UNIQUE INDEX taglines_ci ON taglines(name COLLATE NOCASE);
    CREATE UNIQUE INDEX collections_ci ON collections(name COLLATE NOCASE);
    CREATE UNIQUE INDEX genres_ci ON genres(name COLLATE NOCASE);
    CREATE UNIQUE INDEX countries_ci ON countries(name COLLATE NOCASE);
    CREATE TABLE users (
          id                  INTEGER PRIMARY KEY,
          username            TEXT NOT NULL UNIQUE COLLATE NOCASE,
          password_hash       TEXT NOT NULL,
          is_admin            INTEGER NOT NULL DEFAULT 0,
          api_key_hash        TEXT UNIQUE,
          api_key_hint        TEXT NOT NULL DEFAULT '',
          created_at          REAL NOT NULL,
          password_changed_at REAL NOT NULL
        , theme_dark TEXT NOT NULL DEFAULT '', theme_light TEXT NOT NULL DEFAULT '',
    metadataapi_token_encrypted TEXT NOT NULL DEFAULT '', api_key_encrypted TEXT NOT NULL DEFAULT '');
    CREATE TABLE sessions (
          token_hash   TEXT PRIMARY KEY,
          user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          created_at   REAL NOT NULL,
          last_seen_at REAL NOT NULL,
          user_agent   TEXT NOT NULL DEFAULT ''
        );
    CREATE INDEX sessions_user ON sessions(user_id);
    CREATE TABLE plex_connections (
          id              INTEGER PRIMARY KEY,
          user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          name            TEXT NOT NULL,
          server_url      TEXT NOT NULL DEFAULT '',
          token_encrypted TEXT NOT NULL DEFAULT '',
          client_id       TEXT NOT NULL DEFAULT '',
          update_channel  TEXT NOT NULL DEFAULT 'plex',
          update_release  TEXT NOT NULL DEFAULT '',
          image_base_url  TEXT NOT NULL DEFAULT '',
          created_at      REAL NOT NULL,
          UNIQUE (user_id, name)
        );
    CREATE INDEX plex_connections_user ON plex_connections(user_id);
    CREATE TABLE plex_connection_clients (
          connection_id INTEGER NOT NULL REFERENCES plex_connections(id) ON DELETE CASCADE,
          client_id     TEXT NOT NULL,
          PRIMARY KEY (connection_id, client_id)
        );
    CREATE INDEX plex_connection_clients_client ON plex_connection_clients(client_id);
    CREATE TABLE client_hits (
          client_id  TEXT PRIMARY KEY,
          headers    TEXT NOT NULL DEFAULT '{}',
          count      INTEGER NOT NULL DEFAULT 0,
          first_seen REAL NOT NULL,
          last_seen  REAL NOT NULL,
          last_path  TEXT NOT NULL DEFAULT ''
        );
    CREATE TABLE daily_requests (
          scope TEXT NOT NULL,
          key   TEXT NOT NULL,
          day   TEXT NOT NULL,
          count INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (scope, key, day)
        );
    CREATE INDEX daily_requests_day ON daily_requests(day);
"""

_local = threading.local()
_open: list[tuple[int, sqlite3.Connection]] = []
_lock = threading.Lock()
_current: tuple[str, int] = ('', 0)
_migrated = False


def _discard() -> None:
    global _current, _migrated
    mine = threading.get_ident()
    for owner, conn in _open:
        if owner == mine:
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


class _Held:
    def __init__(self, conn: sqlite3.Connection, key: tuple[str, int]) -> None:
        self.conn = conn
        self.key = key

    def __del__(self) -> None:
        self.conn.close()


def _open_connection(path: str) -> sqlite3.Connection:
    global _migrated
    with _lock:
        conn = sqlite3.connect(path, check_same_thread=False)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute(f'PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}')
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
            conn.execute('PRAGMA foreign_keys=ON')
            if not _migrated:
                _migrate(conn, path)
                _migrated = True
        except BaseException:
            conn.close()
            raise
        _open.append((threading.get_ident(), conn))
    return conn


def connect() -> sqlite3.Connection:
    key = _epoch()
    held: _Held | None = getattr(_local, 'held', None)
    if held is not None and held.key == key:
        return held.conn
    if held is not None:
        held.conn.close()
    Path(key[0]).parent.mkdir(parents=True, exist_ok=True)
    conn = _open_connection(key[0])
    _local.held = _Held(conn, key)
    return conn


def close() -> None:
    with _lock:
        _discard()


_MIGRATIONS: list[str] = [
    _SCHEMA_V1,
]

_ENSURE_DATA = (
    "UPDATE users SET theme_dark = 'sky' WHERE theme_dark = 'day'",
    "UPDATE users SET theme_light = 'sky' WHERE theme_light = 'day'",
)

_ENSURE_INDEXES = (
    'CREATE INDEX IF NOT EXISTS scene_people_person ON scene_people(person_id)',
    'CREATE INDEX IF NOT EXISTS scene_people_role_person ON scene_people(role, person_id)',
    'CREATE INDEX IF NOT EXISTS scene_genres_genre ON scene_genres(genre_id)',
    'CREATE INDEX IF NOT EXISTS scene_collections_collection ON scene_collections(collection_id)',
    'CREATE INDEX IF NOT EXISTS scene_countries_country ON scene_countries(country_id)',
)

_ENSURE_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ('scenes', 'locked_fields', "TEXT NOT NULL DEFAULT '[]'"),
    ('scenes', 'images_locked', 'INTEGER NOT NULL DEFAULT 0'),
    ('scene_images', 'locked', 'INTEGER NOT NULL DEFAULT 0'),
    ('scenes', 'source_url', 'TEXT'),
    ('scenes', 'source_kind', 'TEXT'),
    ('scenes', 'source_json', 'TEXT'),
)


def _ensure_columns(conn: sqlite3.Connection) -> None:
    by_table: dict[str, list[tuple[str, str]]] = {}
    for table, column, decl in _ENSURE_COLUMNS:
        by_table.setdefault(table, []).append((column, decl))
    for table, wanted in by_table.items():
        have = {str(r['name']) for r in conn.execute(f'PRAGMA table_info({table})')}
        for column, decl in wanted:
            if column not in have:
                conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {decl}')
                logger.info('db', f'added column {table}.{column}')
    for statement in _ENSURE_INDEXES:
        conn.execute(statement)
    for statement in _ENSURE_DATA:
        conn.execute(statement)
    conn.commit()


def _migrate(conn: sqlite3.Connection, path: str) -> None:
    version = int(conn.execute('PRAGMA user_version').fetchone()[0])
    if version == 2:
        conn.execute('PRAGMA user_version = 1')
        conn.commit()
        version = 1
        logger.info('db', 'phoenixadult.db restamped to schema v1 - the v2 theme rename folded into the connect-time data pass')
    if version > len(_MIGRATIONS):
        raise RuntimeError(
            f'{path} reports schema v{version}, which this build does not know - it predates the v1 baseline or comes from a newer build. '
            'Check STATE_DB_PATH points at the database you meant'
        )
    for idx, step in enumerate(_MIGRATIONS[version:], start=version + 1):
        conn.executescript(step)
        conn.execute(f'PRAGMA user_version = {idx}')
        conn.commit()
        logger.info('db', f'phoenixadult.db schema at v{idx}')
    _ensure_columns(conn)


# ── Shared Helpers ────────────────────────────────────────────────────────────


class ReconciledConn:
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
    return value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def like_contains(value: str) -> str:
    return f'%{like_escape(value)}%'


def like_prefix(value: str) -> str:
    return f'{like_escape(value)}%'


def dim_id(conn: sqlite3.Connection, table: str, name: str, unique_col: str = 'name') -> int | None:
    if not name:
        return None
    row = conn.execute(f'SELECT id FROM {table} WHERE {unique_col} = ? COLLATE NOCASE', (name,)).fetchone()  # noqa: S608 - fixed table names
    if row is not None:
        return int(row['id'])
    cur = conn.execute(f'INSERT INTO {table}({unique_col}) VALUES(?)', (name,))  # noqa: S608
    return int(cur.lastrowid or 0)
