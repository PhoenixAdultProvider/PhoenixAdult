from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path

from app.clients.base import SearchResult
from app.config.env import env
from app.utils.logging.logger import logger

SearchKey = tuple[str, str, str, str, str]

_STORE_TTL = 7 * 86400.0
_swept = False


def store_dir() -> Path:
    return Path(env.search_queue_dir)


def normalize_text(value: str) -> str:
    return ' '.join(value.lower().split())


def _path(key: SearchKey) -> Path:
    digest = hashlib.sha1('|'.join(key).encode('utf-8')).hexdigest()
    return store_dir() / f'{digest}.json'


def save(key: SearchKey, results: list[SearchResult]) -> None:
    """Empty results are never persisted — a ban/soft-failure window returns [] and must
    retry on the next scan, not poison a week of lookups."""
    global _swept
    if not _swept:
        _swept = True
        _sweep()
    if not results:
        _path(key).unlink(missing_ok=True)
        return
    try:
        store_dir().mkdir(parents=True, exist_ok=True)
        payload = {'key': list(key), 'saved_at': time.time(), 'results': [asdict(r) for r in results]}
        _path(key).write_text(json.dumps(payload), encoding='utf-8')
    except OSError as err:
        logger.warn('search-store', f'could not persist search results: {err}')


def load(key: SearchKey) -> list[SearchResult] | None:
    path = _path(key)
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if time.time() - float(payload.get('saved_at') or 0) > _STORE_TTL:
        path.unlink(missing_ok=True)
        return None
    try:
        results = [SearchResult(**r) for r in payload.get('results') or []]
    except TypeError:
        path.unlink(missing_ok=True)
        return None
    if not results:
        path.unlink(missing_ok=True)
        return None
    return results


def load_similar(key: SearchKey) -> list[SearchResult] | None:
    """Fallback for renamed files: same site+date+language whose stored title is a
    substring of the new one (or vice versa) — a longer filename still hits the store."""
    site, title, date, scene_id, language = key
    if not date or not title:
        return None
    best: tuple[int, SearchKey] | None = None
    try:
        entries = list(store_dir().glob('*.json'))
    except OSError:
        return None
    for path in entries:
        try:
            stored = json.loads(path.read_text(encoding='utf-8')).get('key') or []
        except (OSError, ValueError):
            continue
        if len(stored) != 5 or stored[0] != site or stored[2] != date or stored[3] != scene_id or stored[4] != language:
            continue
        stored_title = str(stored[1])
        if stored_title == title or not (stored_title in title or title in stored_title):
            continue
        if best is None or len(stored_title) > best[0]:
            best = (len(stored_title), (stored[0], stored_title, stored[2], stored[3], stored[4]))
    if best is None:
        return None
    return load(best[1])


def find_title(cur_id: str) -> tuple[str, str] | None:
    """(title, site/subsite) of any stored result with this cur_id — labels update-queue
    entries whose Plex request carries only the rating key."""
    if not cur_id:
        return None
    try:
        entries = list(store_dir().glob('*.json'))
    except OSError:
        return None
    for path in entries:
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        for r in payload.get('results') or []:
            if r.get('cur_id') == cur_id and r.get('title'):
                site = str(r.get('subsite') or (payload.get('key') or [''])[0] or '')
                return str(r['title']), site
    return None


def _sweep() -> None:
    cutoff = time.time() - _STORE_TTL
    try:
        stale = [p for p in store_dir().glob('*.json') if p.stat().st_mtime < cutoff]
    except OSError:
        return
    for p in stale:
        p.unlink(missing_ok=True)
    if stale:
        logger.info('search-store', f'swept {len(stale)} expired search result file(s)')
