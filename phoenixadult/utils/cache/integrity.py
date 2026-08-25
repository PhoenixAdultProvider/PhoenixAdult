from __future__ import annotations

import re
from pathlib import Path

from phoenixadult.config.env import env
from phoenixadult.utils.auth.url_signing import strip_sig
from phoenixadult.utils.cache import scene_store
from phoenixadult.utils.cache.layout import cache_dir

_SNAPSHOT_IMG_RE = re.compile(r'^/cache/(?P<rel>.+)/images/(?P<name>[^/?#]+)$')
_SCAN_CACHE: tuple[str, list[str]] = ('', [])


def snapshot_image_path(url: str, root: Path | None = None) -> Path | None:
    found = _SNAPSHOT_IMG_RE.match(strip_sig(url).split('?')[0])
    if found is None:
        return None

    rel = f'{found["rel"]}/images/{found["name"]}'
    if '..' in rel.split('/'):
        return None

    base = root if root is not None else Path(cache_dir()).resolve()
    target = base / rel
    return target if target.is_relative_to(base) else None


def unrenderable(url: object, root: Path | None = None) -> bool:
    raw = str(url or '').strip()
    if not raw or raw.startswith('/images/local/'):
        return False

    target = snapshot_image_path(raw, root)
    return not target.is_file() if target is not None else True


def missing_image_entries() -> list[str]:
    global _SCAN_CACHE
    token = f'{env.state_db_path}|{env.metadata_cache_dir}|{scene_store.change_token()}'
    cached_token, cached_value = _SCAN_CACHE
    if cached_token == token:
        return list(cached_value)

    root = Path(cache_dir()).resolve()
    broken = [str(row['rel_path']) for row in scene_store.image_check_rows() if unrenderable(row['thumb'], root) or unrenderable(row['art'], root)]
    _SCAN_CACHE = (token, sorted(broken))
    return list(_SCAN_CACHE[1])
