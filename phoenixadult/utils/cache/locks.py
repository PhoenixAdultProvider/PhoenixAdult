from __future__ import annotations

from typing import Any

from phoenixadult.models.metadata import PlexMetadata
from phoenixadult.utils.logging.logger import logger

_CARRY_FIELDS = ('Genre', 'Collection', 'Country', 'Role', 'Director', 'Producer', 'Writer', 'Image')


def carry_emptied_fields(meta: dict[str, Any], previous: dict[str, Any] | None) -> list[str]:
    if not previous:
        return []
    try:
        prior = ((previous.get('MediaContainer') or {}).get('Metadata') or [{}])[0]
    except (AttributeError, IndexError):
        return []
    carried: list[str] = []
    for field in _CARRY_FIELDS:
        if meta.get(field) or not prior.get(field):
            continue
        meta[field] = prior[field]
        carried.append(f'{field}({len(prior[field])})')
    return carried


_LOCK_SCALARS = ('title', 'titleSort', 'summary', 'tagline', 'studio', 'originallyAvailableAt')


_LOCK_LISTS = ('Genre', 'Collection', 'Country', 'Role', 'Director', 'Producer')


def apply_locks(meta: dict[str, Any], previous: dict[str, Any] | None, locks: dict[str, Any]) -> list[str]:
    if not previous:
        return []
    try:
        prior = ((previous.get('MediaContainer') or {}).get('Metadata') or [{}])[0]
    except (AttributeError, IndexError):
        return []
    held: list[str] = []
    fields = set(locks.get('fields') or [])
    for field in _LOCK_SCALARS:
        if field not in fields:
            continue
        if field in prior:
            meta[field] = prior[field]
        else:
            meta.pop(field, None)
        held.append(field)
    if 'data18' in fields:
        if 'data18' in prior:
            meta['data18'] = prior['data18']
        else:
            meta.pop('data18', None)
        held.append('data18')
    for field in _LOCK_LISTS:
        if field not in fields:
            continue
        if prior.get(field):
            meta[field] = prior[field]
        else:
            meta.pop(field, None)
        held.append(field)
    prior_images = prior.get('Image') or []
    if locks.get('imagesLocked'):
        meta['Image'] = prior_images
        for key in ('thumb', 'art'):
            if key in prior:
                meta[key] = prior[key]
            else:
                meta.pop(key, None)
        held.append('Image(set)')
    else:
        pinned = [img for img in prior_images if img.get('locked')]
        if pinned:
            pinned_urls = {str(img.get('url')) for img in pinned}
            fresh = [img for img in meta.get('Image') or [] if str(img.get('url')) not in pinned_urls]
            meta['Image'] = pinned + fresh
            held.append(f'Image({len(pinned)})')
    return held


_PROMOTABLE = (('thumb', 'coverPoster'), ('art', 'background'))


def reconcile_dropped_images(meta: dict[str, Any], image_meta: dict[str, tuple[int, int, int]]) -> None:
    dropped = {key for key, _kind in _PROMOTABLE if key in meta and meta[key] is None}

    kept = [img for img in meta.get('Image') or [] if img.get('url')]
    if kept:
        meta['Image'] = kept
    else:
        meta.pop('Image', None)
    for key, _kind in _PROMOTABLE:
        if meta.get(key) is None:
            meta.pop(key, None)
    for role_key in ('Role', 'Director', 'Producer', 'Writer'):
        for role in meta.get(role_key) or []:
            if role.get('thumb') is None:
                role.pop('thumb', None)
    for rating in meta.get('Rating') or []:
        if rating.get('image') is None:
            rating.pop('image', None)

    def _pixels(img: dict[str, Any]) -> int:
        dims = image_meta.get(str(img.get('url')))
        return dims[0] * dims[1] if dims else 0

    for key, kind in _PROMOTABLE:
        if key not in dropped:
            continue
        candidates = [img for img in kept if img.get('type') == kind]
        if best := max(candidates, key=_pixels, default=None):
            meta[key] = best['url']
            logger.info('meta-cache', f'promoted {str(best["url"]).rsplit("/", 1)[-1]} to {key} after the original was dropped')


def lock_snapshot(md: PlexMetadata) -> dict[str, Any]:
    dump = md.model_dump(by_alias=True, exclude_none=True)
    view: dict[str, Any] = {field: dump.get(field) for field in _LOCK_SCALARS}
    view['data18'] = dump.get('data18')
    for field in _LOCK_LISTS:
        view[field] = [str(entry.get('tag') or '') for entry in dump.get(field) or []]
    return view


def changed_lockables(before: dict[str, Any], after: dict[str, Any]) -> set[str]:
    return {field for field in before if before[field] != after[field]}
