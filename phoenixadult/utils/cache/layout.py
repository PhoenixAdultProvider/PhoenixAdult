from __future__ import annotations

from typing import Any

from phoenixadult.config.env import env
from phoenixadult.registry import find_site
from phoenixadult.utils.helpers.helpers import hash_key, slugify


def enabled() -> bool:
    return env.metadata_cache_enabled


def cache_dir() -> str:
    return env.metadata_cache_dir


BUNDLE_ROOT = 'scenes'


BUNDLE_FILE = 'snapshot.json'


BUNDLE_VERSION = 1


_FANOUT = 2


def _hash(site_name: str, cur_id: str) -> str:
    site = find_site(site_name)
    base = site.name if site else site_name
    return hash_key(slugify(base), cur_id, sep='\n', length=12)


def bundle_path(scene_hash: str) -> str:
    return f'{BUNDLE_ROOT}/{scene_hash[:_FANOUT]}/{scene_hash}'


def is_legacy_path(rel_path: str) -> bool:
    return not rel_path.startswith(f'{BUNDLE_ROOT}/')


def bundle_payload(
    site_name: str, cur_id: str, scene_hash: str, data: dict[str, Any], image_meta: dict[str, tuple[int, int, int]] | None = None
) -> dict[str, Any]:
    return {
        'version': BUNDLE_VERSION,
        'site': site_name,
        'cur_id': cur_id,
        'hash': scene_hash,
        'images': {url: list(dims) for url, dims in (image_meta or {}).items()},
        'response': data,
    }
