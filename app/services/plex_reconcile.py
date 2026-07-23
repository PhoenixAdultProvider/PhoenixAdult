from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import httpx2

from app.config.env import env
from app.registry import PROVIDER_DEFINITIONS
from app.utils import cache as metadata_cache
from app.utils.cache import scene_store
from app.utils.http.client import make_http
from app.utils.logging.logger import logger
from app.utils.plex.rating_key import parse_rating_key

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
    """The provider-side rating key inside one of our guids, else None."""
    if not guid.startswith(prefixes if prefixes is not None else _guid_prefixes()):
        return None
    _, _, tail = guid.partition('://')
    _, _, rating_key = tail.partition('/')
    return rating_key or None


async def _snapshot_tags(rating_key: str) -> dict[str, list[str]] | None:
    """The tag values from this scene's cached snapshot, or None when it was never snapshotted."""
    parsed = parse_rating_key(rating_key)
    if not parsed or not parsed['site_name'] or not parsed['cur_id'] or not metadata_cache.enabled():
        return None
    return await asyncio.to_thread(scene_store.tags_for, parsed['site_name'], parsed['cur_id'])


def _locked_fields(item: dict[str, Any]) -> set[str]:
    return {f['name'] for f in (item.get('Field') or []) if f.get('locked') and f.get('name')}


def _plex_tags(item: dict[str, Any], provider_field: str) -> list[str]:
    return [t['tag'] for t in (item.get(provider_field) or []) if t.get('tag')]


def _removal_reason(value: str, desired_values: list[str]) -> str:
    """Why a Plex-held tag no longer matches the snapshot: a casing/spacing drift of a
    still-emitted value, or a value the scraper simply stopped emitting."""
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
        self.http: httpx2.AsyncClient = make_http({'X-Plex-Token': env.plex_token or '', 'Accept': 'application/json'}, timeout=30.0)

    async def _get(self, path: str, **params: str) -> dict[str, Any]:
        r = await self.http.get(f'{self.base}{path}', params=params)
        r.raise_for_status()
        data = r.json()
        container = data.get('MediaContainer') if isinstance(data, dict) else None
        return container if isinstance(container, dict) else {}

    async def movie_sections(self) -> list[str]:
        container = await self._get('/library/sections')
        return [d['key'] for d in (container.get('Directory') or []) if d.get('type') == 'movie' and d.get('key')]

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
        """Replace the field with exactly these values — removes stale AND fixes recased in one write."""
        params = {'type': '1', 'id': rating_key, f'{tag}.locked': '0'}
        for i, value in enumerate(values):
            params[f'{tag}[{i}].tag.tag'] = value
        r = await self.http.put(f'{self.base}/library/sections/{section}/all', params=params)
        r.raise_for_status()

    async def aclose(self) -> None:
        await self.http.aclose()


async def reconcile(apply: bool = False, limit: int | None = None, fields: set[str] | None = None, sites: set[str] | None = None) -> ReconcileReport:
    """Strip tags Plex still holds that the provider no longer returns. Dry-run by default.
    fields/sites narrow the pass to specific tag types and scraper clients."""
    report = ReconcileReport(applied=apply)
    field_filter = {f for f in (fields or set()) if f in _FIELDS} or set(_FIELDS)
    site_filter = {s.casefold() for s in sites} if sites else None
    client = PlexClient()
    prefixes = _guid_prefixes()
    try:
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
                if limit is not None and report.changed >= limit:
                    continue

                plex_key = str(stub.get('ratingKey') or '')
                entry = ItemReport(rating_key=plex_key, title=stub.get('title') or '', guid=stub.get('guid') or '', site=site_name)

                desired = await _snapshot_tags(rating_key)
                if desired is None:
                    entry.skipped = 'no snapshot'
                    report.skipped_no_snapshot += 1
                    report.items.append(entry)
                    continue

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

                if entry.locked:
                    report.skipped_locked += 1
                if not entry.removals:
                    if entry.locked:
                        report.items.append(entry)
                    continue

                report.changed += 1
                report.items.append(entry)
                if apply:
                    for provider_field, stale in entry.removals.items():
                        if provider_field in ('Collection', 'Genre'):
                            await client.set_tags(section, plex_key, _FIELDS[provider_field], desired[provider_field])
                        else:
                            await client.remove_tags(section, plex_key, _FIELDS[provider_field], stale)
                    logger.info(_TAG, f'{plex_key} "{entry.title}": reconciled {entry.removals}')
    finally:
        await client.aclose()

    verb = 'removed from' if apply else 'would be removed from'
    logger.info(_TAG, f'scanned {report.scanned}, ours {report.matched}, stale tags {verb} {report.changed} item(s)')
    return report
