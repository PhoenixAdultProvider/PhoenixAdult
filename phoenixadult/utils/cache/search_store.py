from __future__ import annotations

import json
import time
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


def dump() -> dict[str, object]:
    conn = db.connect()
    ttl = _ttl_seconds()
    now = time.time()
    snapshot_keys = {str(r['cur_id']): str(r['rel_path']) for r in conn.execute('SELECT cur_id, rel_path FROM scenes')}
    entries: list[dict[str, object]] = []
    by_site: dict[str, int] = {}
    total_results = 0
    expired = 0
    result_rows = conn.execute('SELECT key_hash, pos, cur_id, title, subsite, payload FROM search_results ORDER BY key_hash, pos').fetchall()
    results_by_key: dict[str, list[dict[str, object]]] = {}
    for r in result_rows:
        payload = json.loads(str(r['payload']))
        results_by_key.setdefault(str(r['key_hash']), []).append(
            {
                'pos': int(r['pos']),
                'curId': str(r['cur_id']),
                'title': str(r['title']),
                'subsite': str(r['subsite'] or ''),
                'score': payload.get('score'),
                'releaseDate': payload.get('release_date'),
                'sceneUrl': payload.get('scene_url'),
                'snapshotKey': snapshot_keys.get(str(r['cur_id'])),
            }
        )
    for row in conn.execute('SELECT key_hash, site, title, date, scene_id, language, saved_at FROM searches ORDER BY saved_at DESC'):
        saved_at = float(row['saved_at'])
        is_expired = ttl is not None and now - saved_at > ttl
        expired += 1 if is_expired else 0
        results = results_by_key.get(str(row['key_hash']), [])
        total_results += len(results)
        by_site[str(row['site'])] = by_site.get(str(row['site']), 0) + 1
        entries.append(
            {
                'keyHash': str(row['key_hash']),
                'site': str(row['site']),
                'title': str(row['title']),
                'date': str(row['date'] or ''),
                'sceneId': str(row['scene_id'] or ''),
                'language': str(row['language'] or ''),
                'savedAt': saved_at,
                'expiresAt': saved_at + ttl if ttl is not None else None,
                'expired': is_expired,
                'results': results,
            }
        )
    return {
        'entries': entries,
        'totals': {'searches': len(entries), 'results': total_results, 'expired': expired},
        'sites': dict(sorted(by_site.items())),
        'ttlDays': env.search_store_ttl_days,
    }


def _group_key(row: Mapping[str, Any]) -> str:
    date = str(row['date'] or '')
    return f'{row["site"]}|{date}|{row["sceneId"]}' if date else f'solo|{row["keyHash"]}'


def dump_page(site: str = '', needle: str = '', dupes_only: bool = False, offset: int = 0, limit: int = 50) -> dict[str, object]:
    conn = db.connect()
    ttl = _ttl_seconds()
    now = time.time()

    totals_row = conn.execute('SELECT COUNT(*) AS n FROM searches').fetchone()
    results_row = conn.execute('SELECT COUNT(*) AS n FROM search_results').fetchone()
    by_site = {str(r['site']): int(r['n']) for r in conn.execute('SELECT site, COUNT(*) AS n FROM searches GROUP BY site ORDER BY site')}
    expired_total = 0
    if ttl is not None:
        cut = now - ttl
        expired_total = int(conn.execute('SELECT COUNT(*) AS n FROM searches WHERE saved_at < ?', (cut,)).fetchone()['n'])

    where: list[str] = []
    params: list[object] = []
    if site:
        where.append('site = ?')
        params.append(site)
    if needle:
        like = f'%{needle}%'
        where.append('(LOWER(title) LIKE ? OR key_hash IN (SELECT key_hash FROM search_results WHERE LOWER(title) LIKE ?))')
        params.extend([like, like])
    clause = f' WHERE {" AND ".join(where)}' if where else ''

    light: list[dict[str, Any]] = [
        {
            'keyHash': str(r['key_hash']),
            'site': str(r['site']),
            'title': str(r['title']),
            'date': str(r['date'] or ''),
            'sceneId': str(r['scene_id'] or ''),
            'language': str(r['language'] or ''),
            'savedAt': float(r['saved_at']),
            'expiresAt': float(r['saved_at']) + ttl if ttl is not None else None,
            'expired': ttl is not None and now - float(r['saved_at']) > ttl,
        }
        for r in conn.execute(f'SELECT key_hash, site, title, date, scene_id, language, saved_at FROM searches{clause} ORDER BY saved_at DESC', params)
    ]

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in light:
        grouped.setdefault(_group_key(row), []).append(row)
    groups = [members for members in grouped.values() if not dupes_only or len(members) > 1]
    matched = sum(len(m) for m in groups)
    page = groups[offset : offset + limit]

    wanted = [str(row['keyHash']) for members in page for row in members]
    by_key: dict[str, list[dict[str, Any]]] = {}
    if wanted:
        marks = ','.join('?' * len(wanted))
        rows = conn.execute(
            f'SELECT key_hash, pos, cur_id, title, subsite, payload FROM search_results WHERE key_hash IN ({marks}) ORDER BY key_hash, pos', wanted
        ).fetchall()
        cur_ids = {str(r['cur_id']) for r in rows}
        snapshot_keys: dict[str, str] = {}
        if cur_ids:
            id_marks = ','.join('?' * len(cur_ids))
            snapshot_keys = {
                str(r['cur_id']): str(r['rel_path']) for r in conn.execute(f'SELECT cur_id, rel_path FROM scenes WHERE cur_id IN ({id_marks})', list(cur_ids))
            }
        for r in rows:
            payload = json.loads(str(r['payload']))
            by_key.setdefault(str(r['key_hash']), []).append(
                {
                    'pos': int(r['pos']),
                    'curId': str(r['cur_id']),
                    'title': str(r['title']),
                    'subsite': str(r['subsite'] or ''),
                    'score': payload.get('score'),
                    'releaseDate': payload.get('release_date'),
                    'sceneUrl': payload.get('scene_url'),
                    'snapshotKey': snapshot_keys.get(str(r['cur_id'])),
                }
            )
    for members in page:
        for row in members:
            row['results'] = by_key.get(str(row['keyHash']), [])

    return {
        'groups': page,
        'matched': matched,
        'groupTotal': len(groups),
        'totals': {'searches': int(totals_row['n']), 'results': int(results_row['n']), 'expired': expired_total},
        'sites': by_site,
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
