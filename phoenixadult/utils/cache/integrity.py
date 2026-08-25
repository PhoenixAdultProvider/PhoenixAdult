from __future__ import annotations

import re
from pathlib import Path

from phoenixadult.config.env import env
from phoenixadult.utils.auth.url_signing import strip_sig
from phoenixadult.utils.cache import scene_store
from phoenixadult.utils.cache.layout import cache_dir
from phoenixadult.utils.fs.paths import safe_join

_SNAPSHOT_IMG_RE = re.compile(r'^/cache/(?P<rel>.+)/images/(?P<name>[^/?#]+)$')
_SCAN_CACHE: tuple[str, list[str]] = ('', [])


def snapshot_image_path(url: str) -> Path | None:
    found = _SNAPSHOT_IMG_RE.match(strip_sig(url).split('?')[0])
    if found is None:
        return None

    return safe_join(cache_dir(), f'{found["rel"]}/images/{found["name"]}')


def missing_image_entries() -> list[str]:
    global _SCAN_CACHE
    token = f'{env.state_db_path}|{env.metadata_cache_dir}|{scene_store.change_token()}'
    cached_token, cached_value = _SCAN_CACHE
    if cached_token == token:
        return list(cached_value)

    broken: list[str] = []
    for row in scene_store.image_check_rows():
        for url in (row['thumb'], row['art']):
            target = snapshot_image_path(str(url or ''))
            if target is not None and not target.is_file():
                broken.append(str(row['rel_path']))
                break

    _SCAN_CACHE = (token, sorted(broken))
    return list(_SCAN_CACHE[1])
