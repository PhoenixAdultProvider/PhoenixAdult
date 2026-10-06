from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING
from urllib.parse import unquote

from phoenixadult.config import image_base_url
from phoenixadult.config.env import env
from phoenixadult.models.metadata import CAST_FIELDS, PlexMetadataResponse, PlexRole
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.fs.paths import safe_join
from phoenixadult.utils.images.proxy import LOCAL_IMAGES
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.people import PeopleResolver, to_plex_roles
from phoenixadult.utils.plex.rating_key import to_guid
from phoenixadult.utils.processors.title_case import title_sort

if TYPE_CHECKING:
    from phoenixadult.models.scrape import SceneDetail


def _is_stale_local_thumb(thumb: str) -> bool:
    if LOCAL_IMAGES not in thumb:
        return False
    relpath = unquote(thumb.rsplit(LOCAL_IMAGES, 1)[1].split('?')[0])
    if not relpath:
        return False
    target = safe_join(env.people_cache_dir, relpath)
    return target is None or not target.exists()


async def _resolve_and_fill(
    people: PeopleResolver,
    fill_groups: list[tuple[list[PlexRole], str]],
    *,
    studio: str,
    site_name: str,
    referers: list[str] | None = None,
    cookies: list[str] | None = None,
) -> bool:
    try:
        resolved = await people.resolve_all(studio=studio, site_name=site_name, referers=referers, cookies=cookies)
    except Exception as err:  # noqa: BLE001 — backfill must never break the serve
        logger.warn('meta-cache', f'people-image backfill resolve failed: {err}')
        return False
    changed = False
    for entries, key in fill_groups:
        roles = to_plex_roles(resolved[key], image_base_url(), referers or [], cookies or [])
        by_tag = {p.tag: p for p in roles if p.thumb}
        for r in entries:
            if not r.thumb and r.tag and r.tag in by_tag:
                r.thumb = by_tag[r.tag].thumb
                r.gender = r.gender or by_tag[r.tag].gender
                changed = True
    return changed


_Group = tuple[list[PlexRole], str, str]

_ENQUEUE: dict[str, Callable[[PeopleResolver, PlexRole], None]] = {
    'actor': lambda people, r: people.add_actor(r.tag, '', r.gender or ''),  # type: ignore[arg-type]
    'director': lambda people, r: people.add_director(r.tag, ''),
    'producer': lambda people, r: people.add_producer(r.tag, ''),
}


def _clear_stale_thumbs(groups: list[_Group]) -> tuple[list[str], bool]:
    missing: list[str] = []
    stale_cleared = False
    for entries, _role, key in groups:
        for r in entries:
            if not r.tag:
                continue
            if r.thumb and _is_stale_local_thumb(r.thumb):
                r.thumb = None
                stale_cleared = True
            if not r.thumb:
                missing.append(f'{key}:{r.tag}')
    return missing, stale_cleared


async def _fill_from_scene(
    fetch_detail: Callable[[], Awaitable[SceneDetail | None]], fill_groups: list[tuple[list[PlexRole], str]], studio: str, site_name: str
) -> bool:
    try:
        detail = await fetch_detail()
    except Exception as err:  # noqa: BLE001 — a failed re-fetch just means sources-only
        logger.warn('meta-cache', f'backfill scene re-fetch failed: {err}')
        return False
    if detail is None:
        return False
    scene = PeopleResolver()
    scene.add_detail(detail)
    refs = [detail.art_referer] if detail.art_referer else []
    cks = [detail.art_cookie] if detail.art_cookie else []
    return await _resolve_and_fill(scene, fill_groups, studio=detail.studio or studio, site_name=site_name, referers=refs, cookies=cks)


async def _fill_from_sources(groups: list[_Group], fill_groups: list[tuple[list[PlexRole], str]], studio: str, site_name: str) -> bool:
    sources = PeopleResolver()
    imageless = [(role, r) for entries, role, _key in groups for r in entries if r.tag and not r.thumb]
    for role, r in imageless:
        _ENQUEUE[role](sources, r)
    return bool(imageless) and await _resolve_and_fill(sources, fill_groups, studio=studio, site_name=site_name)


async def backfill_people_images(
    response: PlexMetadataResponse,
    site_name: str,
    *,
    fetch_detail: Callable[[], Awaitable[SceneDetail | None]] | None = None,
) -> bool:
    try:
        md = response.MediaContainer.Metadata[0]
    except (AttributeError, IndexError):
        return False

    groups: list[_Group] = [(md.Role or [], 'actor', 'actors'), (md.Director or [], 'director', 'directors'), (md.Producer or [], 'producer', 'producers')]
    missing, changed = await run_in('fs', _clear_stale_thumbs, groups)
    if not missing:
        logger.debug('meta-cache', f'backfill skip "{md.title}": all cast/crew already have thumbs')
        return False
    logger.debug('meta-cache', f'backfill "{md.title}" ({site_name}): {len(missing)} imageless -> {", ".join(missing)}')

    fill_groups = [(entries, key) for entries, _role, key in groups]
    if fetch_detail is not None and await _fill_from_scene(fetch_detail, fill_groups, md.studio or '', site_name):
        changed = True
    if await _fill_from_sources(groups, fill_groups, md.studio or '', site_name):
        changed = True
    logger.debug('meta-cache', f'backfill "{md.title}": changed={changed}')
    return changed


def backfill_metadata_attrs(response: PlexMetadataResponse) -> bool:
    from phoenixadult.registry import PROVIDER_DEFINITIONS

    changed = False
    for md in response.MediaContainer.Metadata:
        if md.ratingKey:
            guid = to_guid(md.ratingKey, PROVIDER_DEFINITIONS[0].plex_identifier)
            if md.guid != guid:
                md.guid = guid
                changed = True
        if md.contentRating is None:
            md.contentRating = 'XXX'
            changed = True
        if md.isAdult is None:
            md.isAdult = True
            changed = True
        if (sort := title_sort(md.title)) and md.titleSort != sort:
            md.titleSort = sort
            changed = True
        for attr in CAST_FIELDS:
            roles: list[PlexRole] | None = getattr(md, attr)
            for idx, r in enumerate(roles or []):
                if r.order is None:
                    r.order = idx
                    changed = True
    return changed
