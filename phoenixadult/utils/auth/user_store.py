from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Literal

from phoenixadult.utils import db
from phoenixadult.utils.auth.passwords import generate_api_key, generate_session_token, hash_password, hash_token, verify_password

SESSION_TTL_SECONDS = 30 * 24 * 3600
_LAST_SEEN_BUMP_SECONDS = 3600


@dataclass(frozen=True)
class AuthedUser:
    id: int
    username: str
    is_admin: bool
    via: Literal['session', 'api_key']


@dataclass(frozen=True)
class UserRow:
    id: int
    username: str
    is_admin: bool
    api_key_hint: str
    created_at: float


def _row_to_user(row: Any) -> UserRow:
    return UserRow(id=row['id'], username=row['username'], is_admin=bool(row['is_admin']), api_key_hint=row['api_key_hint'], created_at=row['created_at'])


def user_count() -> int:
    return int(db.connect().execute('SELECT COUNT(*) FROM users').fetchone()[0])


def admin_count() -> int:
    return int(db.connect().execute('SELECT COUNT(*) FROM users WHERE is_admin = 1').fetchone()[0])


def create_user(username: str, password: str, is_admin: bool) -> int:
    now = time.time()
    conn = db.connect()
    with conn:
        cur = conn.execute(
            'INSERT INTO users (username, password_hash, is_admin, created_at, password_changed_at) VALUES (?, ?, ?, ?, ?)',
            (username.strip(), hash_password(password), 1 if is_admin else 0, now, now),
        )
    return int(cur.lastrowid or 0)


def list_users() -> list[dict[str, Any]]:
    rows = db.connect().execute('SELECT id, username, is_admin, api_key_hint, created_at FROM users ORDER BY id').fetchall()
    out = []
    for r in rows:
        conns = db.connect().execute('SELECT COUNT(*) FROM plex_connections WHERE user_id = ?', (r['id'],)).fetchone()[0]
        out.append({'id': r['id'], 'username': r['username'], 'isAdmin': bool(r['is_admin']), 'apiKeyHint': r['api_key_hint'], 'connections': conns})
    return out


def get_by_id(user_id: int) -> UserRow | None:
    row = db.connect().execute('SELECT id, username, is_admin, api_key_hint, created_at FROM users WHERE id = ?', (user_id,)).fetchone()
    return _row_to_user(row) if row else None


def verify_login(username: str, password: str) -> UserRow | None:
    row = db.connect().execute('SELECT * FROM users WHERE username = ? COLLATE NOCASE', (username.strip(),)).fetchone()
    if row is None or not verify_password(password, row['password_hash']):
        return None
    return _row_to_user(row)


def set_password(user_id: int, password: str, keep_token_hash: str | None = None) -> None:
    now = time.time()
    conn = db.connect()
    with conn:
        conn.execute('UPDATE users SET password_hash = ?, password_changed_at = ? WHERE id = ?', (hash_password(password), now, user_id))
        if keep_token_hash:
            conn.execute('DELETE FROM sessions WHERE user_id = ? AND token_hash != ?', (user_id, keep_token_hash))
        else:
            conn.execute('DELETE FROM sessions WHERE user_id = ?', (user_id,))


def set_admin(user_id: int, is_admin: bool) -> None:
    conn = db.connect()
    with conn:
        conn.execute('UPDATE users SET is_admin = ? WHERE id = ?', (1 if is_admin else 0, user_id))


def delete_user(user_id: int) -> None:
    conn = db.connect()
    with conn:
        conn.execute('DELETE FROM users WHERE id = ?', (user_id,))


def regenerate_api_key(user_id: int) -> str:
    plain, key_hash, hint = generate_api_key()
    conn = db.connect()
    with conn:
        conn.execute('UPDATE users SET api_key_hash = ?, api_key_hint = ? WHERE id = ?', (key_hash, hint, user_id))
    return plain


def user_for_api_key(presented: str) -> AuthedUser | None:
    row = db.connect().execute('SELECT id, username, is_admin FROM users WHERE api_key_hash = ?', (hash_token(presented),)).fetchone()
    if row is None:
        return None
    return AuthedUser(id=row['id'], username=row['username'], is_admin=bool(row['is_admin']), via='api_key')


def create_session(user_id: int, user_agent: str) -> str:
    plain, token_hash = generate_session_token()
    now = time.time()
    conn = db.connect()
    with conn:
        conn.execute('DELETE FROM sessions WHERE user_id = ? AND last_seen_at < ?', (user_id, now - SESSION_TTL_SECONDS))
        conn.execute(
            'INSERT INTO sessions (token_hash, user_id, created_at, last_seen_at, user_agent) VALUES (?, ?, ?, ?, ?)',
            (token_hash, user_id, now, now, user_agent[:255]),
        )
    return plain


def session_user(token_hash: str, now: float) -> AuthedUser | None:
    conn = db.connect()
    row = conn.execute(
        'SELECT s.last_seen_at, u.id, u.username, u.is_admin FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?',
        (token_hash,),
    ).fetchone()
    if row is None:
        return None
    if now - row['last_seen_at'] > SESSION_TTL_SECONDS:
        with conn:
            conn.execute('DELETE FROM sessions WHERE token_hash = ?', (token_hash,))
        return None
    if now - row['last_seen_at'] > _LAST_SEEN_BUMP_SECONDS:
        with conn:
            conn.execute('UPDATE sessions SET last_seen_at = ? WHERE token_hash = ?', (now, token_hash))
    return AuthedUser(id=row['id'], username=row['username'], is_admin=bool(row['is_admin']), via='session')


def delete_session(token_hash: str) -> None:
    conn = db.connect()
    with conn:
        conn.execute('DELETE FROM sessions WHERE token_hash = ?', (token_hash,))


def sessions_for_user(user_id: int, current_hash: str) -> list[dict[str, Any]]:
    rows = (
        db.connect()
        .execute('SELECT token_hash, created_at, last_seen_at, user_agent FROM sessions WHERE user_id = ? ORDER BY last_seen_at DESC', (user_id,))
        .fetchall()
    )
    return [
        {
            'tokenHash': r['token_hash'],
            'createdAt': r['created_at'],
            'lastSeenAt': r['last_seen_at'],
            'userAgent': r['user_agent'],
            'current': r['token_hash'] == current_hash,
        }
        for r in rows
    ]


def revoke_session(user_id: int, token_hash: str) -> None:
    conn = db.connect()
    with conn:
        conn.execute('DELETE FROM sessions WHERE user_id = ? AND token_hash = ?', (user_id, token_hash))


def oldest_admin_id() -> int | None:
    row = db.connect().execute('SELECT id FROM users WHERE is_admin = 1 ORDER BY id LIMIT 1').fetchone()
    return int(row['id']) if row else None
