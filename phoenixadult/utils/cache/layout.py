from __future__ import annotations

from typing import Any

from phoenixadult.registry import find_site
from phoenixadult.utils.helpers.ids import hash_key
from phoenixadult.utils.helpers.text import slugify

BUNDLE_ROOT = 'scenes'


BUNDLE_FILE = 'snapshot.json'


BUNDLE_VERSION = 1


_FANOUT = 2


def scene_hash_for(site_name: str, cur_id: str) -> str:
    site = find_site(site_name)
    base = site.name if site else site_name
    return hash_key(slugify(base), cur_id, sep='\n', length=12)


def bundle_path(scene_hash: str) -> str:
    return f'{BUNDLE_ROOT}/{scene_hash[:_FANOUT]}/{scene_hash}'


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
