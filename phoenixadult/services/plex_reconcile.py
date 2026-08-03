from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import httpx2

from phoenixadult.config.env import env
from phoenixadult.registry import PROVIDER_DEFINITIONS
from phoenixadult.utils import cache as metadata_cache
from phoenixadult.utils.auth.url_signing import sign_url
from phoenixadult.utils.cache import scene_store
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.http.client import make_http
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.plex.rating_key import parse_rating_key

_TAG = 'plex-reconcile'

_FIELDS: dict[str, str] = {
    'Collection': 'collection',
    'Genre': 'genre',
    'Role': 'actor',
    'Director': 'director',
    'Producer': 'producer',
}


def enabled() -> bool:
    return bool(env.plex_url and env.plex_token)


@dataclass
class ItemReport:
    rating_key: str
    title: str
    guid: str
    site: str = ''
    removals: dict[str, list[str]] = field(default_factory=dict)
    reasons: dict[str, dict[str, str]] = field(default_factory=dict)
    locked: list[str] = field(default_factory=list)
    skipped: str | None = None


@dataclass
class ReconcileReport:
    applied: bool
    scanned: int = 0
    matched: int = 0
    changed: int = 0
    skipped_locked: int = 0
    skipped_no_snapshot: int = 0
    items: list[ItemReport] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            'applied': self.applied,
            'scanned': self.scanned,
            'matched': self.matched,
            'changed': self.changed,
            'skippedLocked': self.skipped_locked,
            'skippedNoSnapshot': self.skipped_no_snapshot,
            'items': [
                {
                    'ratingKey': i.rating_key,
                    'title': i.title,
                    'guid': i.guid,
                    'site': i.site,
                    'removals': i.removals,
                    'reasons': i.reasons,
                    'locked': i.locked,
                    'skipped': i.skipped,
                }
                for i in self.items
            ],
        }


def _guid_prefixes() -> tuple[str, ...]:
    return tuple(f'{p.plex_identifier}://' for p in PROVIDER_DEFINITIONS)


def _our_rating_key(guid: str, prefixes: tuple[str, ...] | None = None) -> str | None:
    if not guid.startswith(prefixes if prefixes is not None else _guid_prefixes()):
        return None
    _, _, tail = guid.partition('://')
    _, _, rating_key = tail.partition('/')
    return rating_key or None


async def _snapshot_tags(rating_key: str) -> dict[str, list[str]] | None:
    parsed = parse_rating_key(rating_key)
    if not parsed or not parsed['site_name'] or not parsed['cur_id'] or not metadata_cache.enabled():
        return None
    return await run_in('store', scene_store.tags_for, parsed['site_name'], parsed['cur_id'])


def _locked_fields(item: dict[str, Any]) -> set[str]:
    return {f['name'] for f in (item.get('Field') or []) if f.get('locked') and f.get('name')}


def _plex_tags(item: dict[str, Any], provider_field: str) -> list[str]:
    return [t['tag'] for t in (item.get(provider_field) or []) if t.get('tag')]


def _removal_reason(value: str, desired_values: list[str]) -> str:
    fold = ' '.join(value.casefold().split())
    for desired in desired_values:
        if ' '.join(desired.casefold().split()) == fold:
            return f'recased to "{desired}"'
    return 'no longer emitted by the scraper'


class PlexClient:
    def __init__(self) -> None:
        if not enabled():
            raise RuntimeError('PLEX_URL and PLEX_TOKEN must both be set')
        self.base = (env.plex_url or '').rstrip('/')
        self.http: httpx2.AsyncClient = make_http(
            {'X-Plex-Token': env.plex_token or '', 'Accept': 'application/json'},
            timeout=30.0,
            limits=httpx2.Limits(max_connections=32, max_keepalive_connections=16, keepalive_expiry=120.0),
        )

    async def _get(self, path: str, **params: str) -> dict[str, Any]:
        started = time.monotonic()
        r = await self.http.get(f'{self.base}{path}', params=params)
        elapsed = time.monotonic() - started
        if elapsed > 5.0:
            logger.warn(_TAG, f'slow Plex response: {elapsed:.1f}s for GET {path}')
        r.raise_for_status()
        data = r.json()
        container = data.get('MediaContainer') if isinstance(data, dict) else None
        return container if isinstance(container, dict) else {}

    async def movie_sections(self) -> list[str]:
        container = await self._get('/library/sections')
        return [d['key'] for d in (container.get('Directory') or []) if d.get('type') == 'movie' and d.get('key')]

    async def movie_libraries(self) -> list[dict[str, str]]:
        container = await self._get('/library/sections')
        return [
            {'key': str(d['key']), 'title': str(d.get('title') or d['key'])}
            for d in (container.get('Directory') or [])
            if d.get('type') == 'movie' and d.get('key')
        ]

    async def section_items(self, section: str) -> list[dict[str, Any]]:
        container = await self._get(f'/library/sections/{section}/all', type='1', includeGuids='1')
        return list(container.get('Metadata') or [])

    async def item(self, rating_key: str) -> dict[str, Any]:
        container = await self._get(f'/library/metadata/{rating_key}', includeFields='1')
        items = container.get('Metadata') or []
        return items[0] if items else {}

    async def remove_tags(self, section: str, rating_key: str, tag: str, values: list[str]) -> None:
        params = {'type': '1', 'id': rating_key, f'{tag}[].tag.tag-': ','.join(values), f'{tag}.locked': '0'}
        r = await self.http.put(f'{self.base}/library/sections/{section}/all', params=params)
        r.raise_for_status()

    async def set_tags(self, section: str, rating_key: str, tag: str, values: list[str]) -> None:
        params = {'type': '1', 'id': rating_key, f'{tag}.locked': '0'}
        for i, value in enumerate(values):
            params[f'{tag}[{i}].tag.tag'] = value
        r = await self.http.put(f'{self.base}/library/sections/{section}/all', params=params)
        r.raise_for_status()

    async def collections(self, section: str) -> list[dict[str, Any]]:
        container = await self._get(f'/library/sections/{section}/collections')
        return list(container.get('Metadata') or [])

    async def artwork(self, rating_key: str, kind: str) -> list[dict[str, Any]]:
        container = await self._get(f'/library/metadata/{rating_key}/{kind}')
        return list(container.get('Metadata') or [])

    async def clear_logo_candidates(self, rating_key: str) -> list[str]:
        container = await self._get(f'/library/metadata/{rating_key}/clearLogos')
        return [str(m.get('key') or '') for m in (container.get('Metadata') or [])]

    async def set_clear_logo(self, rating_key: str, url: str) -> None:
        r = await self.http.post(f'{self.base}/library/metadata/{rating_key}/clearLogos', params={'url': url})
        r.raise_for_status()
        r = await self.http.put(f'{self.base}/library/metadata/{rating_key}/clearLogo', params={'url': url})
        r.raise_for_status()

    async def aclose(self) -> None:
        await self.http.aclose()


_INSPECT_CONCURRENCY = 8

_progress: dict[str, Any] = {'active': False, 'total': 0, 'inspected': 0}


def progress() -> dict[str, Any]:
    return dict(_progress)


async def _inspect_item(
    client: PlexClient, section: str, stub: dict[str, Any], rating_key: str, site_name: str, field_filter: set[str]
) -> tuple[ItemReport, dict[str, list[str]] | None, str]:
    plex_key = str(stub.get('ratingKey') or '')
    entry = ItemReport(rating_key=plex_key, title=stub.get('title') or '', guid=stub.get('guid') or '', site=site_name)

    desired = await _snapshot_tags(rating_key)
    if desired is None:
        entry.skipped = 'no snapshot'
        return entry, None, section

    item = await client.item(plex_key)
    locked = _locked_fields(item)
    for provider_field, plex_tag in _FIELDS.items():
        if provider_field not in field_filter:
            continue
        stale = [t for t in _plex_tags(item, provider_field) if t not in desired[provider_field]]
        if not stale:
            continue
        if plex_tag in locked:
            entry.locked.append(provider_field)
            continue
        entry.removals[provider_field] = stale
        entry.reasons[provider_field] = {value: _removal_reason(value, desired[provider_field]) for value in stale}

    return entry, desired, section


async def reconcile(apply: bool = False, limit: int | None = None, fields: set[str] | None = None, sites: set[str] | None = None) -> ReconcileReport:
    report = ReconcileReport(applied=apply)
    field_filter = {f for f in (fields or set()) if f in _FIELDS} or set(_FIELDS)
    site_filter = {s.casefold() for s in sites} if sites else None
    client = PlexClient()
    prefixes = _guid_prefixes()
    try:
        work: list[tuple[str, dict[str, Any], str, str]] = []
        for section in await client.movie_sections():
            for stub in await client.section_items(section):
                report.scanned += 1
                rating_key = _our_rating_key(stub.get('guid') or '', prefixes)
                if not rating_key:
                    continue
                report.matched += 1
                parsed = parse_rating_key(rating_key)
                site_name = (parsed or {}).get('site_name') or ''
                if site_filter is not None and site_name.casefold() not in site_filter:
                    continue
                work.append((section, stub, rating_key, site_name))

        _progress.update(active=True, total=len(work), inspected=0)
        sem = asyncio.Semaphore(_INSPECT_CONCURRENCY)
        done = False

        async def _guarded(w: tuple[str, dict[str, Any], str, str]) -> tuple[ItemReport, dict[str, list[str]] | None, str] | None:
            async with sem:
                if done:
                    return None
                inspected = await _inspect_item(client, *w, field_filter)
                _progress['inspected'] += 1
                return inspected

        tasks = [asyncio.create_task(_guarded(w)) for w in work]
        try:
            for task in tasks:
                inspected = await task
                if inspected is None:
                    continue
                entry, desired, section = inspected
                if desired is None:
                    report.skipped_no_snapshot += 1
                    report.items.append(entry)
                    continue
                if entry.locked:
                    report.skipped_locked += 1
                if not entry.removals:
                    if entry.locked:
                        report.items.append(entry)
                    continue
                if limit is not None and report.changed >= limit:
                    done = True
                    continue

                report.changed += 1
                report.items.append(entry)
                if apply:
                    for provider_field, stale in entry.removals.items():
                        if provider_field in ('Collection', 'Genre'):
                            await client.set_tags(section, entry.rating_key, _FIELDS[provider_field], desired[provider_field])
                        else:
                            await client.remove_tags(section, entry.rating_key, _FIELDS[provider_field], stale)
                    logger.info(_TAG, f'{entry.rating_key} "{entry.title}": reconciled {entry.removals}')
        finally:
            done = True
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        _progress['active'] = False
        await client.aclose()

    verb = 'removed from' if apply else 'would be removed from'
    logger.info(_TAG, f'scanned {report.scanned}, ours {report.matched}, stale tags {verb} {report.changed} item(s)')
    return report


@dataclass
class CollectionLogoReport:
    applied: bool
    collections: int = 0
    matched: int = 0
    pushed: int = 0
    already: int = 0
    items: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            'applied': self.applied,
            'collections': self.collections,
            'matched': self.matched,
            'pushed': self.pushed,
            'already': self.already,
            'items': self.items,
        }


async def push_collection_logos(apply: bool = False, limit: int | None = None) -> CollectionLogoReport:
    from phoenixadult.config import image_base_url
    from phoenixadult.utils.images import logo_cache

    report = CollectionLogoReport(applied=apply)
    base = image_base_url().rstrip('/')
    cache_root = logo_cache.cache_dir()
    client = PlexClient()
    try:
        for section in await client.movie_sections():
            for col in await client.collections(section):
                report.collections += 1
                title = str(col.get('title') or '')
                plex_key = str(col.get('ratingKey') or '')
                if not title or not plex_key:
                    continue
                hit = await run_in('store', logo_cache.find_logo, title, None)
                if hit is None:
                    continue
                report.matched += 1
                marker = f'/images/local/logos/{hit.relative_to(cache_root).as_posix()}'
                if any(marker in c for c in await client.clear_logo_candidates(plex_key)):
                    report.already += 1
                    continue
                if limit is not None and report.pushed >= limit:
                    continue
                report.pushed += 1
                report.items.append({'title': title, 'ratingKey': plex_key, 'logo': marker.rsplit('/', 1)[-1]})
                if apply:
                    await client.set_clear_logo(plex_key, sign_url(f'{base}{marker}') or f'{base}{marker}')
                    logger.info(_TAG, f'collection "{title}" ({plex_key}): logo {marker}')
    finally:
        await client.aclose()

    verb = 'set on' if apply else 'would be set on'
    logger.info(_TAG, f'collections {report.collections}, logo matches {report.matched}, {verb} {report.pushed} (already {report.already})')
    return report
