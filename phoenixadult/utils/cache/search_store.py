from __future__ import annotations

import json
import time
from dataclasses import asdict

from phoenixadult.clients.base import SearchResult
from phoenixadult.config.env import env
from phoenixadult.utils import db
from phoenixadult.utils.helpers.helpers import hash_key

SearchKey = tuple[str, str, str, str, str]


def _ttl_seconds() -> float | None:
    days = env.search_store_ttl_days
    return days * 86400.0 if days else None


def _expired(saved_at: float) -> bool:
    ttl = _ttl_seconds()
    return ttl is not None and time.time() - saved_at > ttl


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
    if _expired(float(row['saved_at'])):
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
    site, title, date, scene_id, language = key
    if not date:
        return None
    rows = (
        db.connect()
        .execute(
            'SELECT title FROM searches WHERE site = ? AND date = ? AND scene_id = ? AND language = ? ORDER BY saved_at DESC',
            (site, date, scene_id, language),
        )
        .fetchall()
    )
    for row in rows:
        stored_title = str(row['title'])
        if stored_title == title:
            continue
        results = load((site, stored_title, date, scene_id, language))
        if results:
            return results
    return None


def find_title(cur_id: str) -> tuple[str, str] | None:
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
    ttl = _ttl_seconds()
    if ttl is None:
        return 0
    conn = db.connect()
    with conn:
        cur = conn.execute('DELETE FROM searches WHERE saved_at < ?', (time.time() - ttl,))
    return int(cur.rowcount or 0)
