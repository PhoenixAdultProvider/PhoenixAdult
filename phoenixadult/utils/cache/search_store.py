from __future__ import annotations

import json
import sqlite3
import time
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from phoenixadult.config.env import env
from phoenixadult.models.scrape import SearchResult
from phoenixadult.utils import db
from phoenixadult.utils.helpers.ids import hash_key

SearchKey = tuple[str, str, str, str, str]


def _ttl_seconds() -> float | None:
    days = env.search_store_ttl_days
    return days * 86400.0 if days else None


def _expired(saved_at: float) -> bool:
    ttl = _ttl_seconds()
    return ttl is not None and time.time() - saved_at > ttl


def fold_query(value: str) -> str:
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
    try:
        results = [SearchResult(**json.loads(r['payload'])) for r in rows]
    except (TypeError, ValueError):
        results = []
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


def take_for_research(key_hash: str) -> dict[str, str] | None:
    conn = db.connect()
    row = conn.execute('SELECT site, title, date, scene_id, language FROM searches WHERE key_hash = ?', (key_hash,)).fetchone()
    if row is None:
        return None
    purge(key_hash)
    return {
        'search_site': str(row['site']),
        'title': str(row['title']),
        'date': str(row['date'] or ''),
        'scene_id': str(row['scene_id'] or ''),
        'language': str(row['language'] or ''),
    }


def summary() -> dict[str, object]:
    conn = db.connect()
    ttl = _ttl_seconds()
    expired = int(conn.execute('SELECT COUNT(*) AS n FROM searches WHERE saved_at < ?', (time.time() - ttl,)).fetchone()['n']) if ttl is not None else 0
    return {
        'totals': {
            'searches': int(conn.execute('SELECT COUNT(*) AS n FROM searches').fetchone()['n']),
            'results': int(conn.execute('SELECT COUNT(*) AS n FROM search_results').fetchone()['n']),
            'expired': expired,
        },
        'ttlDays': env.search_store_ttl_days,
    }


def purge(key_hash: str) -> bool:
    conn = db.connect()
    with conn:
        cur = conn.execute('DELETE FROM searches WHERE key_hash = ?', (key_hash,))
    return bool(cur.rowcount)


def purge_site(site: str) -> int:
    conn = db.connect()
    with conn:
        cur = conn.execute('DELETE FROM searches WHERE site = ?', (site,))
    return int(cur.rowcount or 0)


def purge_all() -> int:
    conn = db.connect()
    with conn:
        cur = conn.execute('DELETE FROM searches')
    return int(cur.rowcount or 0)


_SEARCH_COLUMNS = 'key_hash, site, title, date, scene_id, language, saved_at'
_RESULT_COLUMNS = 'key_hash, pos, cur_id, title, subsite, payload'


def _search_row(r: Mapping[str, Any], ttl: float | None, now: float) -> dict[str, Any]:
    saved_at = float(r['saved_at'])
    return {
        'keyHash': str(r['key_hash']),
        'site': str(r['site']),
        'title': str(r['title']),
        'date': str(r['date'] or ''),
        'sceneId': str(r['scene_id'] or ''),
        'language': str(r['language'] or ''),
        'savedAt': saved_at,
        'expiresAt': saved_at + ttl if ttl is not None else None,
        'expired': ttl is not None and now - saved_at > ttl,
    }


def _result_row(r: Mapping[str, Any], snapshot_keys: Mapping[str, str]) -> dict[str, object]:
    payload = json.loads(str(r['payload']))
    return {
        'pos': int(r['pos']),
        'curId': str(r['cur_id']),
        'title': str(r['title']),
        'subsite': str(r['subsite'] or ''),
        'score': payload.get('score'),
        'releaseDate': payload.get('release_date'),
        'sceneUrl': payload.get('scene_url'),
        'snapshotKey': snapshot_keys.get(str(r['cur_id'])),
    }


def _by_key(rows: list[Any], snapshot_keys: Mapping[str, str]) -> dict[str, list[dict[str, object]]]:
    out: dict[str, list[dict[str, object]]] = {}
    for r in rows:
        out.setdefault(str(r['key_hash']), []).append(_result_row(r, snapshot_keys))
    return out


def _all_results(conn: sqlite3.Connection) -> dict[str, list[dict[str, object]]]:
    snapshot_keys = {str(r['cur_id']): str(r['rel_path']) for r in conn.execute('SELECT cur_id, rel_path FROM scenes')}
    rows = conn.execute(f'SELECT {_RESULT_COLUMNS} FROM search_results ORDER BY key_hash, pos').fetchall()
    return _by_key(rows, snapshot_keys)


def _results_for(conn: sqlite3.Connection, key_hashes: list[str]) -> dict[str, list[dict[str, object]]]:
    if not key_hashes:
        return {}
    marks = ','.join('?' * len(key_hashes))
    rows = conn.execute(f'SELECT {_RESULT_COLUMNS} FROM search_results WHERE key_hash IN ({marks}) ORDER BY key_hash, pos', key_hashes).fetchall()
    cur_ids = list({str(r['cur_id']) for r in rows})
    id_marks = ','.join('?' * len(cur_ids))
    scenes = conn.execute(f'SELECT cur_id, rel_path FROM scenes WHERE cur_id IN ({id_marks})', cur_ids) if cur_ids else []
    return _by_key(rows, {str(r['cur_id']): str(r['rel_path']) for r in scenes})


def dump() -> dict[str, object]:
    conn = db.connect()
    ttl = _ttl_seconds()
    now = time.time()
    results_by_key = _all_results(conn)
    entries = [
        {**_search_row(row, ttl, now), 'results': results_by_key.get(str(row['key_hash']), [])}
        for row in conn.execute(f'SELECT {_SEARCH_COLUMNS} FROM searches ORDER BY saved_at DESC')
    ]
    return {
        'entries': entries,
        'totals': {'searches': len(entries), 'results': sum(len(e['results']) for e in entries), 'expired': sum(1 for e in entries if e['expired'])},
        'sites': dict(sorted(Counter(str(e['site']) for e in entries).items())),
        'ttlDays': env.search_store_ttl_days,
    }


def _group_key(row: Mapping[str, Any]) -> str:
    date = str(row['date'] or '')
    return f'{row["site"]}|{date}|{row["sceneId"]}' if date else f'solo|{row["keyHash"]}'


def _search_filter(site: str, needle: str) -> tuple[str, list[object]]:
    where: list[str] = []
    params: list[object] = []
    if site:
        where.append('site = ?')
        params.append(site)
    if needle:
        like = db.like_contains(needle)
        where.append("(LOWER(title) LIKE ? ESCAPE '\\' OR key_hash IN (SELECT key_hash FROM search_results WHERE LOWER(title) LIKE ? ESCAPE '\\'))")
        params.extend([like, like])
    return (f' WHERE {" AND ".join(where)}' if where else ''), params


def _store_totals(conn: sqlite3.Connection, ttl: float | None, now: float) -> dict[str, int]:
    searches = int(conn.execute('SELECT COUNT(*) AS n FROM searches').fetchone()['n'])
    results = int(conn.execute('SELECT COUNT(*) AS n FROM search_results').fetchone()['n'])
    expired = int(conn.execute('SELECT COUNT(*) AS n FROM searches WHERE saved_at < ?', (now - ttl,)).fetchone()['n']) if ttl is not None else 0
    return {'searches': searches, 'results': results, 'expired': expired}


def _groups(conn: sqlite3.Connection, site: str, needle: str, dupes_only: bool, ttl: float | None, now: float) -> list[list[dict[str, Any]]]:
    clause, params = _search_filter(site, needle)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for r in conn.execute(f'SELECT {_SEARCH_COLUMNS} FROM searches{clause} ORDER BY saved_at DESC', params):
        row = _search_row(r, ttl, now)
        grouped.setdefault(_group_key(row), []).append(row)
    return [members for members in grouped.values() if not dupes_only or len(members) > 1]


def dump_page(site: str = '', needle: str = '', dupes_only: bool = False, offset: int = 0, limit: int = 50) -> dict[str, object]:
    conn = db.connect()
    ttl = _ttl_seconds()
    now = time.time()
    groups = _groups(conn, site, needle, dupes_only, ttl, now)
    page = groups[offset : offset + limit]
    by_key = _results_for(conn, [str(row['keyHash']) for members in page for row in members])
    for members in page:
        for row in members:
            row['results'] = by_key.get(str(row['keyHash']), [])
    return {
        'groups': page,
        'matched': sum(len(m) for m in groups),
        'groupTotal': len(groups),
        'totals': _store_totals(conn, ttl, now),
        'sites': {str(r['site']): int(r['n']) for r in conn.execute('SELECT site, COUNT(*) AS n FROM searches GROUP BY site ORDER BY site')},
        'ttlDays': env.search_store_ttl_days,
        'pageSize': limit,
    }


def sweep_expired() -> int:
    ttl = _ttl_seconds()
    if ttl is None:
        return 0
    conn = db.connect()
    with conn:
        cur = conn.execute('DELETE FROM searches WHERE saved_at < ?', (time.time() - ttl,))
    return int(cur.rowcount or 0)
