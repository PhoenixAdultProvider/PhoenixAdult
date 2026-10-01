from __future__ import annotations

import shutil
from typing import Any, TypedDict

from phoenixadult.config.env import env
from phoenixadult.registry import find_site, provider_name_for, provider_name_tokens
from phoenixadult.utils.cache import scene_store
from phoenixadult.utils.cache.duplicates import stale_duplicate_entries
from phoenixadult.utils.cache.scene_store import ALL_SCENES, SceneFilter
from phoenixadult.utils.fs.paths import safe_join
from phoenixadult.utils.helpers.data18 import mapping_slug
from phoenixadult.utils.logging.logger import logger


class UiEntry(TypedDict):
    key: str
    provider: str
    site: str
    cur_id: str
    hash: str
    title: str
    studio: str
    tagline: str
    collections: list[str]
    actors: list[str]
    genres: int
    date: str
    thumb: str
    images: int
    mtime: float
    data18_id: str
    data18_type: str
    data18_manual: bool
    data18_also: str
    mapping_slug: str


def _ui_entry(row: scene_store.SceneRow) -> UiEntry:

    rel = row['rel_path']
    return {
        'key': rel,
        'provider': provider_name_for(row['site']) or row['site'],
        'site': row['site'],
        'cur_id': row['cur_id'],
        'hash': rel.rsplit('/', 1)[-1],
        'title': row['title'],
        'studio': row['studio'],
        'tagline': row['tagline'],
        'collections': row['collections'],
        'actors': row['actors'],
        'genres': row['genres'],
        'date': row['release_date'],
        'thumb': row['thumb'],
        'images': row['images'],
        'mtime': row['updated_at'],
        'data18_id': row['data18_id'],
        'data18_type': row['data18_type'],
        'data18_manual': row['data18_manual'],
        'data18_also': row['data18_also'],
        'mapping_slug': mapping_slug(row['title'], row['tagline'] or row['studio'] or None) or '',
    }


def entries() -> list[UiEntry]:
    rows, _total = scene_store.query_entry_rows(ALL_SCENES, limit=-1)
    return [_ui_entry(row) for row in rows]


def provider_sites(provider: str) -> list[str]:
    tokens = provider_name_tokens(provider)
    return tokens if tokens or find_site(provider) else [provider]


def entries_page(
    filters: SceneFilter = ALL_SCENES, *, sort: str = 'updated_at', direction: str = 'desc', limit: int = 200, offset: int = 0
) -> tuple[list[UiEntry], int]:
    rows, total = scene_store.query_entry_rows(filters, sort=sort, direction=direction, limit=limit, offset=offset)
    return [_ui_entry(row) for row in rows], total


def studios(filters: SceneFilter = ALL_SCENES) -> list[str]:
    return scene_store.studio_names(filters)


def facets(filters: SceneFilter = ALL_SCENES) -> dict[str, Any]:
    values = scene_store.facet_values(filters)
    sites = values.pop('sites', [])
    values['providers'] = sorted({provider_name_for(site) or site for site in sites}, key=str.casefold)
    return values


def change_token() -> str:
    return scene_store.change_token()


def purge(key: str) -> bool:
    if not scene_store.delete(key):
        return False
    target = safe_join(env.metadata_cache_dir, key)
    if target is not None:
        shutil.rmtree(target, ignore_errors=True)
    logger.info('meta-cache', f'purged snapshot {key}')
    return True


def purge_duplicates() -> int:
    return sum(1 for rel in stale_duplicate_entries() if purge(rel))
