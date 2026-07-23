from __future__ import annotations

import json
import time
from dataclasses import asdict

from app.clients.base import SearchResult
from app.utils import db
from app.utils.helpers.helpers import hash_key

SearchKey = tuple[str, str, str, str, str]

_STORE_TTL = 7 * 86400.0


def normalize_text(value: str) -> str:
    return ' '.join(value.lower().split())


def _key_hash(key: SearchKey) -> str:
    return hash_key(*key, sep='|')


def _write(key: SearchKey, results: list[SearchResult], saved_at: float) -> None:
    conn = db.connect()
    kh = _key_hash(key)
    with conn:
        conn.execute(
            'INSERT OR REPLACE INTO searches(key_hash, site, title, date, scene_id, language, saved_at) VALUES(?, ?, ?, ?, ?, ?, ?)',
            (kh, *key, saved_at),
        )
        conn.execute('DELETE FROM search_results WHERE key_hash = ?', (kh,))
        conn.executemany(
            'INSERT INTO search_results(key_hash, pos, cur_id, title, subsite, payload) VALUES(?, ?, ?, ?, ?, ?)',
            [(kh, i, r.cur_id, r.title, r.subsite or '', json.dumps(asdict(r))) for i, r in enumerate(results)],
        )


def save(key: SearchKey, results: list[SearchResult]) -> None:
    """Empty results are never persisted — a ban/soft-failure window returns [] and must
    retry on the next scan, not poison a week of lookups."""
    conn = db.connect()
    if not results:
        with conn:
            conn.execute('DELETE FROM searches WHERE key_hash = ?', (_key_hash(key),))
        return
    _write(key, results, time.time())


def load(key: SearchKey) -> list[SearchResult] | None:
    conn = db.connect()
    kh = _key_hash(key)
    row = conn.execute('SELECT saved_at FROM searches WHERE key_hash = ?', (kh,)).fetchone()
    if row is None:
        return None
    if time.time() - float(row['saved_at']) > _STORE_TTL:
        with conn:
            conn.execute('DELETE FROM searches WHERE key_hash = ?', (kh,))
        return None
    rows = conn.execute('SELECT payload FROM search_results WHERE key_hash = ? ORDER BY pos', (kh,)).fetchall()
    results = [SearchResult(**json.loads(r['payload'])) for r in rows]
    if not results:
        with conn:
            conn.execute('DELETE FROM searches WHERE key_hash = ?', (kh,))
        return None
    return results


def load_similar(key: SearchKey) -> list[SearchResult] | None:
    """Fallback for renamed files: same site+date+language whose stored title is a
    substring of the new one (or vice versa) — a longer filename still hits the store."""
    site, title, date, scene_id, language = key
    if not date or not title:
        return None
    rows = (
        db.connect()
        .execute('SELECT title FROM searches WHERE site = ? AND date = ? AND scene_id = ? AND language = ?', (site, date, scene_id, language))
        .fetchall()
    )
    best: str | None = None
    for row in rows:
        stored_title = str(row['title'])
        if stored_title == title or not (stored_title in title or title in stored_title):
            continue
        if best is None or len(stored_title) > len(best):
            best = stored_title
    if best is None:
        return None
    return load((site, best, date, scene_id, language))


def find_title(cur_id: str) -> tuple[str, str] | None:
    """(title, site/subsite) of any stored result with this cur_id — labels update-queue
    entries whose Plex request carries only the rating key."""
    if not cur_id:
        return None
    row = (
        db.connect()
        .execute(
            'SELECT r.title, r.subsite, s.site FROM search_results r JOIN searches s ON s.key_hash = r.key_hash WHERE r.cur_id = ? LIMIT 1',
            (cur_id,),
        )
        .fetchone()
    )
    if row is None:
        return None
    return str(row['title']), str(row['subsite'] or row['site'])


def sweep_expired() -> int:
    conn = db.connect()
    with conn:
        cur = conn.execute('DELETE FROM searches WHERE saved_at < ?', (time.time() - _STORE_TTL,))
    return int(cur.rowcount or 0)
