from __future__ import annotations

import threading
import time
import uuid
from typing import Any

from pydantic import ConfigDict

from phoenixadult.models.camel import CamelModel
from phoenixadult.utils import db
from phoenixadult.utils.auth.server_secret import decrypt, encrypt

_union_lock = threading.Lock()
_union_cache: tuple[int, str, frozenset[str]] | None = None
_generation = 0


class Connection(CamelModel):
    model_config = ConfigDict(alias_generator=CamelModel.model_config['alias_generator'], populate_by_name=True, frozen=True)

    id: int
    user_id: int
    name: str
    server_url: str
    client_id: str
    update_channel: str
    update_release: str
    image_base_url: str
    has_token: bool
    allowed_clients: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude={'user_id'})


def _bump() -> None:
    global _generation
    with _union_lock:
        _generation += 1


def _row_to_connection(row: Any, allowed: tuple[str, ...]) -> Connection:
    return Connection(
        id=row['id'],
        user_id=row['user_id'],
        name=row['name'],
        server_url=row['server_url'],
        client_id=row['client_id'],
        update_channel=row['update_channel'],
        update_release=row['update_release'],
        image_base_url=row['image_base_url'],
        has_token=bool(row['token_encrypted']),
        allowed_clients=allowed,
    )


def _allowed_for(conn: Any, connection_id: int) -> tuple[str, ...]:
    rows = conn.execute('SELECT client_id FROM plex_connection_clients WHERE connection_id = ? ORDER BY client_id', (connection_id,)).fetchall()
    return tuple(r['client_id'] for r in rows)


def list_for_user(user_id: int) -> list[Connection]:
    conn = db.connect()
    rows = conn.execute('SELECT * FROM plex_connections WHERE user_id = ? ORDER BY id', (user_id,)).fetchall()
    return [_row_to_connection(r, _allowed_for(conn, r['id'])) for r in rows]


def get_owned(user_id: int, connection_id: int) -> Connection | None:
    conn = db.connect()
    row = conn.execute('SELECT * FROM plex_connections WHERE id = ? AND user_id = ?', (connection_id, user_id)).fetchone()
    return _row_to_connection(row, _allowed_for(conn, row['id'])) if row else None


def get(connection_id: int) -> Connection | None:
    conn = db.connect()
    row = conn.execute('SELECT * FROM plex_connections WHERE id = ?', (connection_id,)).fetchone()
    return _row_to_connection(row, _allowed_for(conn, row['id'])) if row else None


def create(user_id: int, name: str, client_id: str = '') -> int:
    conn = db.connect()
    with conn:
        cur = conn.execute(
            'INSERT INTO plex_connections (user_id, name, client_id, created_at) VALUES (?, ?, ?, ?)',
            (user_id, name.strip(), client_id or uuid.uuid4().hex, time.time()),
        )
    _bump()
    return int(cur.lastrowid or 0)


_EDITABLE = {
    'name': 'name',
    'serverUrl': 'server_url',
    'updateChannel': 'update_channel',
    'updateRelease': 'update_release',
    'imageBaseUrl': 'image_base_url',
    'clientId': 'client_id',
}


def update_fields(connection_id: int, fields: dict[str, Any]) -> None:
    sets = [(column, str(fields[key]).strip()) for key, column in _EDITABLE.items() if key in fields]
    if not sets:
        return
    assignments = ', '.join(f'{column} = ?' for column, _ in sets)
    conn = db.connect()
    with conn:
        conn.execute(f'UPDATE plex_connections SET {assignments} WHERE id = ?', (*[v for _, v in sets], connection_id))  # noqa: S608 - fixed column names
    _bump()


def delete(connection_id: int) -> None:
    conn = db.connect()
    with conn:
        conn.execute('DELETE FROM plex_connections WHERE id = ?', (connection_id,))
    _bump()


def set_allowed_clients(connection_id: int, client_ids: list[str]) -> None:
    cleaned = {c.strip() for c in client_ids if c.strip()}
    conn = db.connect()
    with conn:
        conn.execute('DELETE FROM plex_connection_clients WHERE connection_id = ?', (connection_id,))
        conn.executemany('INSERT INTO plex_connection_clients (connection_id, client_id) VALUES (?, ?)', [(connection_id, c) for c in sorted(cleaned)])
    _bump()


def save_token(connection_id: int, plain_token: str) -> None:
    stored = encrypt(plain_token) if plain_token else ''
    conn = db.connect()
    with conn:
        conn.execute('UPDATE plex_connections SET token_encrypted = ? WHERE id = ?', (stored, connection_id))
    _bump()


def token_for(connection_id: int) -> str | None:
    row = db.connect().execute('SELECT token_encrypted FROM plex_connections WHERE id = ?', (connection_id,)).fetchone()
    if row is None or not row['token_encrypted']:
        return None
    return decrypt(row['token_encrypted'])


def _read_union() -> frozenset[str]:
    rows = db.connect().execute('SELECT DISTINCT client_id FROM plex_connection_clients').fetchall()
    return frozenset(r['client_id'] for r in rows)


def allowed_client_union() -> frozenset[str]:
    global _union_cache
    from phoenixadult.config.env import env

    db_path = env.state_db_path
    with _union_lock:
        generation = _generation
        if _union_cache is not None and _union_cache[0] == generation and _union_cache[1] == db_path:
            return _union_cache[2]
    union = _read_union()
    with _union_lock:
        _union_cache = (generation, db_path, union)
    return union


def invalidate() -> None:
    global _union_cache
    with _union_lock:
        _union_cache = None


_MIGRATED_KEYS = ('PLEX_URL', 'PLEX_TOKEN', 'PLEX_CLIENT_ID', 'PLEX_CLIENT_ALLOWLIST', 'PLEX_UPDATE_CHANNEL', 'PLEX_UPDATE_RELEASE')


def migrate_env_connection() -> str | None:
    import os
    from urllib.parse import urlsplit

    from phoenixadult.config.env_overrides import clear_override
    from phoenixadult.utils.auth import user_store

    url = (os.environ.get('PLEX_URL') or '').strip().rstrip('/')
    token = (os.environ.get('PLEX_TOKEN') or '').strip()
    if not url and not token:
        return None
    if db.connect().execute('SELECT COUNT(*) FROM plex_connections').fetchone()[0]:
        return None
    owner = user_store.oldest_admin_id()
    if owner is None:
        return None

    name = urlsplit(url).hostname or 'Migrated Server'
    connection_id = create(owner, name, (os.environ.get('PLEX_CLIENT_ID') or '').strip())
    update_fields(
        connection_id,
        {
            'serverUrl': url,
            'updateChannel': (os.environ.get('PLEX_UPDATE_CHANNEL') or 'plex').strip(),
            'updateRelease': (os.environ.get('PLEX_UPDATE_RELEASE') or '').strip(),
        },
    )
    if token:
        save_token(connection_id, token)
    allowlist = [c.strip() for c in (os.environ.get('PLEX_CLIENT_ALLOWLIST') or '').split(',') if c.strip()]
    if allowlist:
        set_allowed_clients(connection_id, allowlist)
    for key in _MIGRATED_KEYS:
        clear_override(key)
    return name
