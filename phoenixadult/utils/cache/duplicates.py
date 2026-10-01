from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from phoenixadult.config.env import env
from phoenixadult.utils.cache import scene_store
from phoenixadult.utils.cache.layout import scene_hash_for
from phoenixadult.utils.helpers.ids import b64url_decode, b64url_encode, scene_url_id, split_subsite
from phoenixadult.utils.plex.rating_key import parse_rating_key

_SCAN_MEMO: dict[str, tuple[str, Any]] = {}


def _by_change[T](key: str, build: Callable[[], T]) -> T:
    token = f'{env.state_db_path}|{scene_store.change_token()}'
    cached = _SCAN_MEMO.get(key)
    if cached is not None and cached[0] == token:
        return cached[1]  # type: ignore[no-any-return]
    value = build()
    _SCAN_MEMO[key] = (token, value)
    return value


def duplicate_entries() -> list[str]:
    return list(_by_change('duplicate_entries', _duplicate_entries))


def _duplicate_entries() -> list[str]:
    keys = scene_store.scene_keys()
    by_hash = {scene_hash: rel for scene_hash, rel, _rating_key in keys}
    stale: set[str] = set()
    for _scene_hash, rel, rating_key in keys:
        parsed = parse_rating_key(rating_key)
        if not parsed or not parsed['cur_id'] or not parsed['site_name']:
            continue
        try:
            payload, subsite = split_subsite(b64url_decode(parsed['cur_id']))
        except ValueError:
            continue
        if not subsite:
            continue
        old_rel = by_hash.get(scene_hash_for(parsed['site_name'], b64url_encode(payload)))
        if old_rel and old_rel != rel:
            stale.add(old_rel)
    return sorted(stale)


_CONTENT_NORM_RE = re.compile(r'[^a-z0-9]+')


def _content_norm(value: object) -> str:
    return _CONTENT_NORM_RE.sub('', str(value or '').lower())


def _content_duplicate_groups() -> list[list[tuple[str, float]]]:
    return _by_change('content_groups', _build_content_groups)


def _build_content_groups() -> list[list[tuple[str, float]]]:
    groups: dict[str, list[tuple[str, float]]] = {}
    for row in scene_store.dup_candidate_rows():
        title = _content_norm(row['title'])
        if not title:
            continue
        key = '|'.join(
            (title, _content_norm(row['release_date']), _content_norm(row['studio_name']), _content_norm(row['tagline_name']), scene_url_id(row['source_url']))
        )
        groups.setdefault(key, []).append((str(row['rel_path']), float(row['updated_at'] or 0)))
    return [members for members in groups.values() if len(members) > 1]


def content_duplicate_entries() -> list[str]:
    matched = {rel for members in _content_duplicate_groups() for rel, _ in members}
    return sorted(matched | set(duplicate_entries()))


_STALE_DUP_CACHE: tuple[str, list[str] | None] = ('', None)


def stale_duplicate_entries() -> list[str]:
    global _STALE_DUP_CACHE
    token = f'{env.state_db_path}|{scene_store.change_token()}'
    cached_token, cached_value = _STALE_DUP_CACHE
    if cached_token == token and cached_value is not None:
        return list(cached_value)
    stale = set(duplicate_entries())
    for members in _content_duplicate_groups():
        keep = max(members, key=lambda m: (m[1], m[0]))[0]
        stale.update(rel for rel, _ in members if rel != keep)
    result = sorted(stale)
    _STALE_DUP_CACHE = (token, result)
    return list(result)
