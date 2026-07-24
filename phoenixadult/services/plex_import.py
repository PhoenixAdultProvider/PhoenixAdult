from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx2
from PIL import Image as PILImage

from phoenixadult.mappers.metadata_mapper import build_artwork
from phoenixadult.models.metadata import PlexImage, PlexMetadataResponse
from phoenixadult.registry import PROVIDER_DEFINITIONS, find_site
from phoenixadult.services.plex_reconcile import PlexClient, _our_rating_key
from phoenixadult.utils import cache as metadata_cache
from phoenixadult.utils.cache import _hash, scene_store
from phoenixadult.utils.fs.paths import safe_join
from phoenixadult.utils.images.image_classifier import classify_image
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.plex import legacy_guid
from phoenixadult.utils.plex.rating_key import parse_rating_key, to_guid, to_rating_key
from phoenixadult.utils.processors.title_case import title_sort

_TAG = 'plex-import'
_STAGING = '_plex-import'
_MAX_ITEMS = 500
_CONCURRENCY = 4
_ROLE_FIELDS = ('Role', 'Director', 'Writer', 'Producer')


@dataclass
class ItemReport:
    rating_key: str
    title: str
    status: str
    site: str = ''
    cur_id: str = ''
    detail: str = ''


@dataclass
class ImportReport:
    applied: bool
    section: str = ''
    library: str = ''
    scanned: int = 0
    imported: int = 0
    importable: int = 0
    skipped_existing: int = 0
    unresolved: int = 0
    failed: int = 0
    items_truncated: int = 0
    items: list[ItemReport] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            'applied': self.applied,
            'section': self.section,
            'library': self.library,
            'scanned': self.scanned,
            'imported': self.imported,
            'importable': self.importable,
            'skippedExisting': self.skipped_existing,
            'unresolved': self.unresolved,
            'failed': self.failed,
            'itemsTruncated': self.items_truncated,
            'items': [
                {'ratingKey': i.rating_key, 'title': i.title, 'status': i.status, 'site': i.site, 'curId': i.cur_id, 'detail': i.detail} for i in self.items
            ],
        }

    def add(self, item: ItemReport) -> None:
        if len(self.items) < _MAX_ITEMS:
            self.items.append(item)
        else:
            self.items_truncated += 1


def _resolve(guid: str, studio: str) -> tuple[str, str] | None:
    """(site name, cur_id) for a Plex item: our own guid first, then the retired bundle's numeric
    site id, then the studio field — so a legacy id we no longer ship still resolves by name."""
    if rating_key := _our_rating_key(guid):
        parsed = parse_rating_key(rating_key)
        if parsed and parsed['site_name'] and parsed['cur_id']:
            return str(parsed['site_name']), str(parsed['cur_id'])
    if decoded := legacy_guid.decode(guid):
        return decoded
    cur_id = legacy_guid.payload(guid)
    site = find_site(studio) if studio else None
    return (site.name, cur_id) if site and cur_id else None


def _tags(item: dict[str, Any], key: str) -> list[dict[str, str]]:
    return [{'tag': t['tag']} for t in (item.get(key) or []) if t.get('tag')]


def _roles(item: dict[str, Any], key: str) -> list[dict[str, Any]]:
    """Cast/crew without thumbs — headshots are left to the people pipeline, not imported."""
    out: list[dict[str, Any]] = []
    for order, entry in enumerate(item.get(key) or []):
        if not entry.get('tag'):
            continue
        role: dict[str, Any] = {'tag': entry['tag'], 'order': order}
        if entry.get('role'):
            role['role'] = entry['role']
        out.append(role)
    return out


def _candidate_ref(candidate: dict[str, Any]) -> str:
    """The bytes a candidate points at. Posters and arts list the same agent images under
    different buckets, so the trailing hash — not the bucket — identifies a duplicate."""
    ref = str(candidate.get('ratingKey') or candidate.get('key') or '')
    return ref.rsplit('/', 1)[-1] if ref else ''


def _candidate_url(client: PlexClient, candidate: dict[str, Any]) -> str:
    """A fetchable URL for one candidate: a server path when Plex gives one, otherwise the photo
    endpoint, which is the only way to read an agent-supplied `metadata://` image."""
    key = str(candidate.get('key') or '')
    if key.startswith('http'):
        return key
    if key.startswith('/'):
        return f'{client.base}{key}'
    ref = str(candidate.get('ratingKey') or key or '')
    return f'{client.base}/photo/:/transcode?url={quote(ref, safe="")}&width=4096&height=4096&minSize=0&upscale=0'


async def _stage_image(client: PlexClient, staging: Path, url: str, name: str) -> tuple[str, int, int] | None:
    """Pull one Plex-hosted image into a staging dir and return its /cache/ URL plus dimensions, so
    the snapshot write adopts the bytes off disk and the Plex token never reaches stored metadata."""
    try:
        r = await client.http.get(url)
        r.raise_for_status()
    except (httpx2.HTTPError, ValueError) as err:
        logger.warn(_TAG, f'image fetch failed {url.split("?")[0]}: {err!r}')
        return None
    ext = '.png' if 'png' in r.headers.get('content-type', '') else '.jpg'
    images = staging / 'images'
    images.mkdir(parents=True, exist_ok=True)
    target = images / f'{name}{ext}'
    target.write_bytes(r.content)
    try:
        with PILImage.open(target) as im:
            width, height = im.size
    except (OSError, ValueError) as err:
        logger.warn(_TAG, f'image unreadable {target.name}: {err!r}')
        target.unlink(missing_ok=True)
        return None
    return f'/cache/{_STAGING}/{staging.name}/images/{name}{ext}', width, height


async def _stage_artwork(client: PlexClient, staging: Path, rating_key: str) -> list[PlexImage]:
    """Every poster and art candidate Plex holds, deduplicated across the two buckets and put
    through the mapper's own artwork pipeline, so shape decides the kind — never the bucket."""
    probed: list[dict[str, Any]] = []
    seen: set[str] = set()
    for bucket, hint in (('posters', 'poster'), ('arts', 'art')):
        try:
            candidates = await client.artwork(rating_key, bucket)
        except httpx2.HTTPError as err:
            logger.warn(_TAG, f'{bucket} listing failed for {rating_key}: {err!r}')
            continue
        for candidate in candidates:
            ref = _candidate_ref(candidate)
            if ref and ref in seen:
                continue
            seen.add(ref)
            result = await _stage_image(client, staging, _candidate_url(client, candidate), f'{hint}-{len(probed):02d}')
            if result is None:
                continue
            url, width, height = result
            probed.append({'url': url, 'dims': {'width': width, 'height': height}, 'image_class': classify_image(width, height).image_class})
    return build_artwork(probed)


def _build(item: dict[str, Any], site_name: str, cur_id: str, images: list[PlexImage]) -> PlexMetadataResponse:
    """Assemble a provider response from one Plex item, keyed so a later serve finds it."""
    title = str(item.get('title') or '')
    date = str(item.get('originallyAvailableAt') or '')
    rating_key = to_rating_key(cur_id, site_name, date or None)
    identifier = PROVIDER_DEFINITIONS[0].plex_identifier
    metadata: dict[str, Any] = {
        'type': 'movie',
        'ratingKey': rating_key,
        'guid': to_guid(rating_key, identifier),
        'title': title,
        'titleSort': title_sort(title),
        'contentRating': 'XXX',
        'isAdult': True,
    }
    for key, source in (('summary', 'summary'), ('originallyAvailableAt', 'originallyAvailableAt'), ('studio', 'studio')):
        if item.get(source):
            metadata[key] = item[source]
    for key in ('year', 'duration', 'rating', 'audienceRating'):
        if item.get(key) is not None:
            metadata[key] = item[key]
    metadata['Genre'] = _tags(item, 'Genre')
    metadata['Collection'] = _tags(item, 'Collection')
    if country := _tags(item, 'Country'):
        metadata['Country'] = country
    for key in _ROLE_FIELDS:
        if roles := _roles(item, key):
            metadata[key] = roles
    if poster := next((img.url for img in images if img.type == 'coverPoster'), ''):
        metadata['thumb'] = poster
    if background := next((img.url for img in images if img.type == 'background'), ''):
        metadata['art'] = background
    metadata['Image'] = [{'url': img.url, 'type': img.type} for img in images]
    return PlexMetadataResponse.model_validate({'MediaContainer': {'identifier': identifier, 'size': 1, 'Metadata': [metadata]}})


async def _import_one(client: PlexClient, stub: dict[str, Any], report: ImportReport, apply: bool, overwrite: bool = False) -> None:
    rating_key = str(stub.get('ratingKey') or '')
    title = str(stub.get('title') or '')
    resolved = _resolve(str(stub.get('guid') or ''), str(stub.get('studio') or ''))
    if resolved is None:
        report.unresolved += 1
        report.add(ItemReport(rating_key, title, 'unresolved', detail='no site match for its guid or studio'))
        return
    site_name, cur_id = resolved
    if not overwrite and scene_store.has(_hash(site_name, cur_id)):
        report.skipped_existing += 1
        report.add(ItemReport(rating_key, title, 'skipped', site_name, cur_id, 'already cached'))
        return
    report.importable += 1
    if not apply:
        report.add(ItemReport(rating_key, title, 'importable', site_name, cur_id))
        return

    staging = safe_join(metadata_cache.cache_dir(), f'{_STAGING}/{_hash(site_name, cur_id)}')
    try:
        item = await client.item(rating_key)
        if not item:
            raise ValueError('item vanished from Plex')
        images: list[PlexImage] = []
        if staging is not None:
            images = await _stage_artwork(client, staging, rating_key)
        response = _build(item, site_name, cur_id, images)
        if await metadata_cache.write(site_name, cur_id, response):
            report.imported += 1
            report.add(ItemReport(rating_key, title, 'imported', site_name, cur_id, f'{len(images)} images'))
        else:
            report.failed += 1
            report.add(ItemReport(rating_key, title, 'failed', site_name, cur_id, 'snapshot write rejected'))
    except (httpx2.HTTPError, OSError, ValueError) as err:
        report.failed += 1
        report.add(ItemReport(rating_key, title, 'failed', site_name, cur_id, repr(err)))
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)


async def libraries() -> list[dict[str, str]]:
    """Movie sections on the configured server, for the import dropdown."""
    client = PlexClient()
    try:
        return await client.movie_libraries()
    finally:
        await client.aclose()


async def import_library(section: str, apply: bool = False, limit: int | None = None, overwrite: bool = False) -> ImportReport:
    """Snapshot every scene in one Plex library into the metadata cache. Dry-run by default;
    scenes already cached are left alone so a stored fresh scrape is never overwritten."""
    report = ImportReport(applied=apply, section=section)
    if not metadata_cache.enabled():
        raise RuntimeError('METADATA_CACHE_ENABLE must be on to import')
    client = PlexClient()
    try:
        for lib in await client.movie_libraries():
            if lib['key'] == section:
                report.library = lib['title']
        stubs = await client.section_items(section)
        if limit:
            stubs = stubs[:limit]
        report.scanned = len(stubs)
        sem = asyncio.Semaphore(_CONCURRENCY)

        async def _run(stub: dict[str, Any]) -> None:
            async with sem:
                await _import_one(client, stub, report, apply, overwrite)

        await asyncio.gather(*(_run(stub) for stub in stubs))
    finally:
        await client.aclose()
    logger.info(
        _TAG,
        f'{"imported" if apply else "scanned"} {report.library or section}: {report.imported}/{report.importable} new, '
        f'{report.skipped_existing} cached, {report.unresolved} unresolved, {report.failed} failed',
    )
    return report
