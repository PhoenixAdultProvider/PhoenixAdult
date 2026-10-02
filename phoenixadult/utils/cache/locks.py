from __future__ import annotations

from typing import Any

from phoenixadult.models.metadata import CREDIT_FIELDS, PlexMetadata
from phoenixadult.utils.logging.logger import logger

_CARRY_FIELDS = ('Genre', 'Collection', 'Country', 'Role', 'Director', 'Producer', 'Writer', 'Image')


def _prior(previous: dict[str, Any] | None) -> dict[str, Any] | None:
    if not previous:
        return None
    try:
        prior: dict[str, Any] = ((previous.get('MediaContainer') or {}).get('Metadata') or [{}])[0]
    except (AttributeError, IndexError):
        return None
    return prior


def carry_emptied_fields(meta: dict[str, Any], previous: dict[str, Any] | None) -> list[str]:
    prior = _prior(previous)
    if prior is None:
        return []
    carried: list[str] = []
    for field in _CARRY_FIELDS:
        if meta.get(field) or not prior.get(field):
            continue
        meta[field] = prior[field]
        carried.append(f'{field}({len(prior[field])})')
    return carried


_LOCK_SCALARS = ('title', 'titleSort', 'summary', 'tagline', 'studio', 'originallyAvailableAt', 'data18')


_LOCK_LISTS = ('Genre', 'Collection', 'Country', 'Role', 'Director', 'Producer')


def _restore(meta: dict[str, Any], prior: dict[str, Any], field: str, keep: bool) -> None:
    if keep:
        meta[field] = prior[field]
    else:
        meta.pop(field, None)


def _hold_fields(meta: dict[str, Any], prior: dict[str, Any], fields: set[str]) -> list[str]:
    scalars = [field for field in _LOCK_SCALARS if field in fields]
    lists = [field for field in _LOCK_LISTS if field in fields]
    for field in scalars:
        _restore(meta, prior, field, field in prior)
    for field in lists:
        _restore(meta, prior, field, bool(prior.get(field)))
    return scalars + lists


def _hold_images(meta: dict[str, Any], prior: dict[str, Any], images_locked: bool) -> list[str]:
    prior_images = prior.get('Image') or []
    if images_locked:
        meta['Image'] = prior_images
        for key in ('thumb', 'art'):
            _restore(meta, prior, key, key in prior)
        return ['Image(set)']
    pinned = [img for img in prior_images if img.get('locked')]
    if not pinned:
        return []
    pinned_urls = {str(img.get('url')) for img in pinned}
    meta['Image'] = pinned + [img for img in meta.get('Image') or [] if str(img.get('url')) not in pinned_urls]
    return [f'Image({len(pinned)})']


def apply_locks(meta: dict[str, Any], previous: dict[str, Any] | None, locks: dict[str, Any]) -> list[str]:
    prior = _prior(previous)
    if prior is None:
        return []
    return _hold_fields(meta, prior, set(locks.get('fields') or [])) + _hold_images(meta, prior, bool(locks.get('imagesLocked')))


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
    for role_key in CREDIT_FIELDS:
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
