from __future__ import annotations

import asyncio
import json
import re
import shutil
import sqlite3
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import unquote

import httpx2
from PIL import Image as PILImage

from phoenixadult.config import config, image_base_url
from phoenixadult.config.env import env
from phoenixadult.models.metadata import PlexCollection, PlexCountry, PlexData18, PlexGenre, PlexImage, PlexMetadata, PlexMetadataResponse, PlexRole
from phoenixadult.registry import ResolvedSiteInfo, find_site, provider_name_for, provider_name_tokens
from phoenixadult.utils.cache import scene_store
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.fs.paths import safe_join
from phoenixadult.utils.genres import NormalizeGenresOptions, normalize_genres
from phoenixadult.utils.helpers.helpers import hash_key, slugify
from phoenixadult.utils.images.ext import ext_from
from phoenixadult.utils.images.image_fetcher import fetch_image
from phoenixadult.utils.images.proxy import proxy_params
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.people import PeopleManager, apply_name_aliases, to_plex_roles
from phoenixadult.utils.plex.rating_key import parse_rating_key
from phoenixadult.utils.processors.studio_name import normalize_studio
from phoenixadult.utils.processors.text_normalize import normalize_text
from phoenixadult.utils.processors.title_case import title_case, title_sort

if TYPE_CHECKING:
    from phoenixadult.clients.base import SceneDetail

_ERROR_TITLE_RE = re.compile(r'\b(404|403|401|500|not found|forbidden|access denied|just a moment|attention required|page not found|error)\b', re.IGNORECASE)

_write_locks: dict[str, asyncio.Lock] = {}
_write_lock_users: dict[str, int] = {}


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


# ── Data18 Manual-Mapping Change Detection ────────────────────────────────────


def _data18_fingerprint(response: PlexMetadataResponse) -> str:
    from phoenixadult.clients.aggregators.data18 import manual_mapping_url, mapping_slug

    try:
        md = response.MediaContainer.Metadata[0]
    except (AttributeError, IndexError):
        return ''
    return manual_mapping_url(mapping_slug(md.title or '', md.tagline or md.studio)) or ''


def _stored_data18(response: PlexMetadataResponse) -> dict[str, str] | None:
    try:
        d = response.MediaContainer.Metadata[0].data18
    except (AttributeError, IndexError):
        return None
    return {'type': d.type, 'id': d.id} if d else None


def data18_remap_needed(response: PlexMetadataResponse, site_name: str) -> bool:
    from phoenixadult.clients.aggregators.data18 import data18_ref

    if not env.data18_enabled:
        return False
    site = find_site(site_name)
    if not site or not site.scraper_config.data18_enrichment:
        return False
    manual = data18_ref(_data18_fingerprint(response))
    return manual is not None and manual != _stored_data18(response)


def data18_backfill_needed(response: PlexMetadataResponse, site_name: str) -> bool:
    if not env.data18_enabled:
        return False
    site = find_site(site_name)
    if not site or not site.scraper_config.data18_enrichment:
        return False
    return any(md.data18 is None and md.title for md in response.MediaContainer.Metadata)


async def backfill_data18(response: PlexMetadataResponse, site_name: str) -> bool:
    from datetime import datetime

    from phoenixadult.clients.aggregators.data18 import Data18Client, data18_ref, mapping_slug
    from phoenixadult.models.metadata import PlexData18

    if not env.data18_enabled:
        return False
    site = find_site(site_name)
    if not site or not site.scraper_config.data18_enrichment:
        return False
    pending = [md for md in response.MediaContainer.Metadata if md.data18 is None and md.title]
    if not pending:
        return False

    client = Data18Client()
    changed = False
    for md in pending:
        try:
            date_obj = datetime.fromisoformat(md.originallyAvailableAt) if md.originallyAvailableAt else None
        except ValueError:
            date_obj = None
        providers = [p for p in (md.studio, md.tagline) if p]
        try:
            url = await client.find_scene_url(mapping_slug(md.title, md.tagline or md.studio), md.title, providers, date_obj)
        except Exception as err:  # noqa: BLE001 — backfill must never break the serve
            logger.warn('meta-cache', f'data18 backfill resolve failed for "{md.title}": {err}')
            continue
        if ref := data18_ref(url):
            md.data18 = PlexData18.model_validate(ref)
            changed = True
    return changed


# ── Read ─────────────────────────────────────────────────────────────────────


def read(site_name: str, cur_id: str) -> dict[str, Any] | None:
    if not enabled():
        return None
    loaded = scene_store.load(_hash(site_name, cur_id))
    if loaded is None:
        return None
    rebased = _rebase(loaded, config.base_url.rstrip('/'), image_base_url().rstrip('/'))
    return rebased if isinstance(rebased, dict) else None


# ── Write ────────────────────────────────────────────────────────────────────

_SNAPSHOT_IMG_RE = re.compile(r'^/cache/(?P<rel>.+)/images/(?P<name>[^/?#]+)$')


def _snapshot_file(url: str, base: str) -> tuple[Path, str] | None:
    path = url[len(base) :] if url.startswith(f'{base}/') else url
    match = _SNAPSHOT_IMG_RE.match(path)
    if match is None:
        return None
    target = safe_join(cache_dir(), f'{match["rel"]}/images/{match["name"]}')
    return None if target is None else (target, match['name'])


def _probe_file(path: Path) -> tuple[tuple[int, int, int], bool] | None:
    from phoenixadult.utils.images.image_fetcher import is_solid

    try:
        with PILImage.open(path) as im:
            width, height = im.size
            im.draft(None, (160, 160))
            solid = is_solid(im.convert('RGB') if im.mode == 'P' else im)
        return (width, height, path.stat().st_size), solid
    except (OSError, ValueError):
        return None


def _rebase(obj: Any, base: str, people_base: str) -> Any:
    if isinstance(obj, dict):
        return {k: _rebase(v, base, people_base) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_rebase(v, base, people_base) for v in obj]
    if isinstance(obj, str):
        marker = '/images/local/'
        if marker in obj:
            return f'{people_base}{obj[obj.index(marker) :]}'
        if obj.startswith('/cache/') or obj.startswith('/images/'):
            return f'{base}{obj}'
    return obj


async def write(site_name: str, cur_id: str, response: PlexMetadataResponse, *, allow_clear: bool = False) -> bool:
    if not enabled():
        return False
    try:
        md0 = response.MediaContainer.Metadata[0]
        title = (md0.title or '').strip()
    except (AttributeError, IndexError):
        return False
    if not title or _ERROR_TITLE_RE.search(title):
        logger.info('meta-cache', f'skip snapshot (title looks like an error): {title!r}')
        return False

    scene_hash = _hash(site_name, cur_id)
    rel_path = bundle_path(scene_hash)
    final_dir = safe_join(cache_dir(), rel_path)
    if final_dir is None:
        return False

    lock = _write_locks.setdefault(scene_hash, asyncio.Lock())
    _write_lock_users[scene_hash] = _write_lock_users.get(scene_hash, 0) + 1
    try:
        async with lock:
            return await _write_locked(response, site_name, cur_id, scene_hash, rel_path, final_dir, allow_clear)
    finally:
        _write_lock_users[scene_hash] -= 1
        if _write_lock_users[scene_hash] == 0:
            del _write_lock_users[scene_hash]
            _write_locks.pop(scene_hash, None)


_CARRY_FIELDS = ('Genre', 'Collection', 'Country', 'Role', 'Director', 'Producer', 'Writer', 'Image')


def _carry_emptied_fields(meta: dict[str, Any], previous: dict[str, Any] | None) -> list[str]:
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


_PROMOTABLE = (('thumb', 'coverPoster'), ('art', 'background'))


def _reconcile_dropped_images(meta: dict[str, Any], image_meta: dict[str, tuple[int, int, int]]) -> None:
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


async def _write_locked(
    response: PlexMetadataResponse, site_name: str, cur_id: str, scene_hash: str, rel_path: str, final_dir: Path, allow_clear: bool = False
) -> bool:
    tmp_dir = final_dir.parent / f'{scene_hash}.tmp'

    data = response.model_dump(by_alias=True, exclude_none=True)
    meta: dict[str, Any] = data['MediaContainer']['Metadata'][0]

    if not allow_clear:
        previous = await run_in('store', scene_store.load, scene_hash)
        if carried := _carry_emptied_fields(meta, previous):
            logger.warn('meta-cache', f'scrape returned nothing for {", ".join(carried)} on {rel_path} — kept the stored values')
    base = config.base_url.rstrip('/')
    counter = [0]
    image_meta: dict[str, tuple[int, int, int]] = {}

    def _reset_tmp() -> None:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        tmp_dir.mkdir(parents=True, exist_ok=True)

    await run_in('fs', _reset_tmp)
    try:
        sem = asyncio.Semaphore(6)

        def _targets() -> list[tuple[dict[str, Any], str, str]]:
            found: list[tuple[dict[str, Any], str, str]] = [(meta, 'thumb', 'poster'), (meta, 'art', 'art')]
            found.extend((img, 'url', 'img') for img in meta.get('Image', []))
            for role_key in ('Role', 'Director', 'Producer', 'Writer'):
                found.extend((role, 'thumb', 'role') for role in meta.get(role_key, []))
            found.extend((rating, 'image', 'rating') for rating in meta.get('Rating', []))
            return [(obj, key, hint) for obj, key, hint in found if obj.get(key)]

        targets = _targets()
        kept_names = {hit[1] for obj, key, _hint in targets if (hit := _snapshot_file(str(obj[key]), base)) is not None}

        def _relativize(u: str) -> str:
            return u[len(base) :] if u.startswith(f'{base}/') else u

        def _keep(source: Path, name: str) -> tuple[str, tuple[int, int, int] | None, bool] | None:
            if not source.is_file():
                return None
            img_dir = tmp_dir / 'images'
            img_dir.mkdir(exist_ok=True)
            copied = img_dir / name
            shutil.copy2(source, copied)
            probed = _probe_file(copied)
            if probed is not None and probed[1]:
                copied.unlink(missing_ok=True)
                return f'/cache/{rel_path}/images/{name}', None, True
            return f'/cache/{rel_path}/images/{name}', (probed[0] if probed else None), False

        def _store_bytes(name: str, payload: bytes) -> None:
            img_dir = tmp_dir / 'images'
            img_dir.mkdir(exist_ok=True)
            (img_dir / name).write_bytes(payload)

        async def localize(url: str | None, hint: str) -> str | None:
            if not url:
                return url
            if '/images/local/' in url:
                return url[url.index('/images/local/') :]
            if (hit := _snapshot_file(url, base)) is not None:
                if (kept := await run_in('fs', _keep, *hit)) is not None:
                    local, probed, solid = kept
                    if solid:
                        logger.info('meta-cache', f'dropped a solid-colour image from {rel_path}: {hit[1]}')
                        return None
                    if probed:
                        image_meta[local] = probed
                    return local
                logger.debug('meta-cache', f'kept snapshot image missing on disk {url}')
                return _relativize(url)
            target, referers, cookies = proxy_params(url)
            while (name := f'{hint}-{counter[0]:02d}{ext_from("", target)}') in kept_names:
                counter[0] += 1
            counter[0] += 1
            try:
                async with sem:
                    entry = await fetch_image(target, referers or None, cookies or None)
                if entry.solid:
                    logger.info('meta-cache', f'skipped a solid-colour image for {rel_path}: {target}')
                    return None
                await run_in('fs', _store_bytes, name, entry.data)
                local = f'/cache/{rel_path}/images/{name}'
                image_meta[local] = (entry.width, entry.height, len(entry.data))
                return local
            except (httpx2.HTTPError, ValueError, OSError) as err:
                logger.debug('meta-cache', f'image download failed {target}: {err!r}')
                return _relativize(url)

        by_url: dict[str, list[tuple[dict[str, Any], str]]] = {}
        hints: dict[str, str] = {}
        for obj, key, hint in targets:
            url = str(obj[key])
            by_url.setdefault(url, []).append((obj, key))
            hints.setdefault(url, hint)

        async def _assign(url: str, holders: list[tuple[dict[str, Any], str]]) -> None:
            resolved = await localize(url, hints[url])
            for obj, key in holders:
                obj[key] = resolved

        await asyncio.gather(*(_assign(url, holders) for url, holders in by_url.items()))
        _reconcile_dropped_images(meta, image_meta)

        def _write_bundle() -> None:
            payload = bundle_payload(site_name, cur_id, scene_hash, data, image_meta)
            (tmp_dir / BUNDLE_FILE).write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')

        await run_in('fs', _write_bundle)

        def _promote() -> None:
            if final_dir.exists():
                shutil.rmtree(final_dir, ignore_errors=True)
            tmp_dir.rename(final_dir)

        await run_in('fs', _promote)
    except OSError as err:
        await run_in('fs', shutil.rmtree, tmp_dir, ignore_errors=True)
        logger.warn('meta-cache', f'snapshot write failed {rel_path}: {err}')
        return False

    try:
        await run_in('store', scene_store.upsert, site_name, cur_id, scene_hash, rel_path, data, image_meta)
    except sqlite3.Error as err:
        logger.warn('meta-cache', f'snapshot db write failed {rel_path}: {err}')
        return False
    logger.info('meta-cache', f'snapshot saved {rel_path} ({meta.get("title", "")})')
    return True


# ── Management (UI) ──────────────────────────────────────────────────────────


def _ui_entry(row: dict[str, Any]) -> dict[str, Any]:
    from phoenixadult.clients.aggregators.data18 import mapping_slug

    rel = row['rel_path']
    return {
        'key': rel,
        'provider': provider_name_for(row['site']) or row['site'],
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
        'mapping_slug': mapping_slug(row['title'], row['tagline'] or row['studio'] or None) or '',
    }


def entries() -> list[dict[str, Any]]:
    rows, _total = scene_store.query_entry_rows(limit=-1)
    return [_ui_entry(row) for row in rows]


def _provider_sites(provider: str) -> list[str]:
    tokens = provider_name_tokens(provider)
    return tokens if tokens or find_site(provider) else [provider]


def entries_page(
    *,
    studio: str = '',
    query: str = '',
    year: str = '',
    month: str = '',
    day: str = '',
    tagline: str = '',
    collection: str = '',
    data18: str = '',
    actor: str = '',
    genre: str = '',
    cast: str = '',
    director: str = '',
    producer: str = '',
    provider: str = '',
    dups_only: bool = False,
    dup_paths: list[str] | None = None,
    sort: str = 'updated_at',
    direction: str = 'desc',
    limit: int = 500,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    rows, total = scene_store.query_entry_rows(
        studio=studio,
        query=query,
        year=year,
        month=month,
        day=day,
        tagline=tagline,
        collection=collection,
        data18=data18,
        actor=actor,
        genre=genre,
        cast=cast,
        director=director,
        producer=producer,
        provider_sites=_provider_sites(provider) if provider else None,
        dup_paths=(duplicate_entries() if dup_paths is None else dup_paths) if dups_only else None,
        sort=sort,
        direction=direction,
        limit=limit,
        offset=offset,
    )
    return [_ui_entry(row) for row in rows], total


def _facet_scope(active: dict[str, Any]) -> dict[str, Any]:
    scope = {k: v for k, v in active.items() if k != 'provider'}
    provider = str(active.get('provider') or '')
    scope['provider_sites'] = _provider_sites(provider) if provider else None
    return scope


def studios(**active: Any) -> list[str]:
    return scene_store.studio_names(**_facet_scope(active))


def actor_suggestions(query: str = '', limit: int = 50) -> list[str]:
    return scene_store.actor_names(query, limit)


def facets(**active: Any) -> dict[str, Any]:
    values = scene_store.facet_values(**_facet_scope(active))
    sites = values.pop('sites', [])
    values['providers'] = sorted({provider_name_for(site) or site for site in sites}, key=str.casefold)
    return values


def change_token() -> str:
    return scene_store.change_token()


def purge(key: str) -> bool:
    if not scene_store.delete(key):
        return False
    target = safe_join(cache_dir(), key)
    if target is not None:
        shutil.rmtree(target, ignore_errors=True)
    logger.info('meta-cache', f'purged snapshot {key}')
    return True


_EDITABLE_TAGS = {'Genre': PlexGenre, 'Collection': PlexCollection, 'Country': PlexCountry}
_EDITABLE_ROLES = ('Role', 'Director', 'Producer')


def backfill_studio(response: PlexMetadataResponse, site: ResolvedSiteInfo) -> bool:
    from phoenixadult.clients import get_client

    client = get_client(site.scraper_config.type)
    derived = client.studio_for(site) if client else None
    if not derived:
        return False
    try:
        md = response.MediaContainer.Metadata[0]
    except (AttributeError, IndexError):
        return False
    if normalize_studio(derived) == md.studio:
        return False
    logger.info('meta-cache', f'restudioed "{md.title}": {md.studio!r} -> {normalize_studio(derived)!r}')
    md.studio = normalize_studio(derived)
    if md.tagline and md.tagline == md.studio:
        md.tagline = None
    return True


def drop_stale_people_thumbs(response: PlexMetadataResponse, site_name: str, cur_id: str) -> bool:
    if not scene_store.take_force_refresh(_hash(site_name, cur_id)):
        return False
    try:
        md = response.MediaContainer.Metadata[0]
    except (AttributeError, IndexError):
        return False
    cleared = 0
    for attr in _EDITABLE_ROLES:
        for role in getattr(md, attr) or []:
            if role.thumb and '/images/local/' in role.thumb:
                role.thumb = None
                cleared += 1
    logger.info('meta-cache', f'forced people re-push for "{md.title}": {cleared} headshot(s) to re-resolve')
    return True


def load_for_edit(key: str) -> dict[str, Any] | None:
    identity = scene_store.identity_for(key)
    if identity is None:
        return None
    loaded = scene_store.load(key.rsplit('/', 1)[-1])
    return loaded if isinstance(loaded, dict) else None


def _apply_data18_edit(md: PlexMetadata, fields: dict[str, Any]) -> None:
    if 'data18_id' not in fields:
        return
    edited = str(fields['data18_id'] or '').strip()
    if not edited:
        md.data18 = None
        return
    raw_type = str(fields.get('data18_type') or '').strip() or (md.data18.type if md.data18 else '')
    kind: Literal['scene', 'movie'] = 'movie' if raw_type == 'movie' else 'scene'
    if md.data18 and md.data18.id == edited and md.data18.type == kind:
        return
    md.data18 = PlexData18(type=kind, id=edited, manual=True)


def _apply_edits(md: PlexMetadata, fields: dict[str, Any]) -> None:
    if title := str(fields.get('title', '') or '').strip():
        md.title = title
    for attr in ('titleSort', 'summary', 'tagline', 'studio', 'originallyAvailableAt'):
        if attr in fields:
            setattr(md, attr, str(fields[attr] or '').strip() or None)
    date = md.originallyAvailableAt or ''
    md.year = int(date[0:4]) if date[0:4].isdigit() else None
    for attr, model in _EDITABLE_TAGS.items():
        if attr in fields:
            tags = [str(t).strip() for t in fields[attr] or [] if str(t).strip()]
            setattr(md, attr, [model(tag=tag) for tag in dict.fromkeys(tags)] or None)
    existing = {attr: {r.tag: r for r in (getattr(md, attr) or [])} for attr in _EDITABLE_ROLES}
    for attr in _EDITABLE_ROLES:
        if attr not in fields:
            continue
        kept: list[PlexRole] = []
        for pos, raw in enumerate(fields[attr] or []):
            tag = str(raw).strip()
            if not tag or any(r.tag == tag for r in kept):
                continue
            prior = existing[attr].get(tag) or PlexRole(tag=tag)
            kept.append(PlexRole(tag=tag, role=prior.role, thumb=prior.thumb, gender=prior.gender, order=pos))
        setattr(md, attr, kept or None)
    _apply_data18_edit(md, fields)
    if 'Image' in fields:
        images = [PlexImage(url=str(i.get('url', '')).strip(), type=str(i.get('type', '')).strip() or 'coverPoster') for i in fields['Image'] or []]
        md.Image = [i for i in images if i.url] or None
        md.thumb = next((i.url for i in md.Image or [] if i.type == 'coverPoster'), None)
        md.art = next((i.url for i in md.Image or [] if i.type == 'background'), None)


async def save_edits(key: str, fields: dict[str, Any]) -> str | None:
    identity = scene_store.identity_for(key)
    loaded = load_for_edit(key)
    if identity is None or loaded is None:
        return None
    site_name, cur_id = identity
    response = PlexMetadataResponse.model_validate(loaded)
    try:
        md = response.MediaContainer.Metadata[0]
    except (AttributeError, IndexError):
        return None
    _apply_edits(md, fields)
    if not await write(site_name, cur_id, response, allow_clear=True):
        return None
    return bundle_path(_hash(site_name, cur_id))


def duplicate_entries() -> list[str]:
    from phoenixadult.utils.helpers.helpers import b64url_decode, b64url_encode, split_subsite

    keys = scene_store.scene_keys()
    by_hash = {scene_hash: rel for scene_hash, rel, _rating_key in keys}
    stale: set[str] = set()
    for _scene_hash, rel, rating_key in keys:
        parsed = parse_rating_key(rating_key)
        if not parsed or not parsed['cur_id'] or not parsed['site_name']:
            continue
        try:
            payload, subsite = split_subsite(b64url_decode(parsed['cur_id']))
        except ValueError:
            continue
        if not subsite:
            continue
        old_rel = by_hash.get(_hash(parsed['site_name'], b64url_encode(payload)))
        if old_rel and old_rel != rel:
            stale.add(old_rel)
    return sorted(stale)


def purge_duplicates() -> int:
    return sum(1 for rel in duplicate_entries() if purge(rel))


# ── People-Image Backfill ─────────────────────────────────────────────────────


def _is_stale_local_thumb(thumb: str) -> bool:
    marker = '/images/local/'
    if marker not in thumb:
        return False
    relpath = unquote(thumb.rsplit(marker, 1)[1].split('?')[0])
    if not relpath:
        return False
    target = safe_join(env.people_cache_dir, relpath)
    return target is None or not target.exists()


async def _resolve_and_fill(
    people: PeopleManager,
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

    groups: list[tuple[list[PlexRole], str, str]] = [
        (md.Role or [], 'actor', 'actors'),
        (md.Director or [], 'director', 'directors'),
        (md.Producer or [], 'producer', 'producers'),
    ]

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
    if not missing:
        logger.debug('meta-cache', f'backfill skip "{md.title}": all cast/crew already have thumbs')
        return False
    logger.debug('meta-cache', f'backfill "{md.title}" ({site_name}): {len(missing)} imageless -> {", ".join(missing)}')

    fill_groups = [(entries, key) for entries, _role, key in groups]
    changed = stale_cleared

    if fetch_detail is not None:
        try:
            detail = await fetch_detail()
        except Exception as err:  # noqa: BLE001 — a failed re-fetch just means sources-only
            logger.warn('meta-cache', f'backfill scene re-fetch failed: {err}')
            detail = None
        if detail is not None:
            scene = PeopleManager()
            for a in detail.actors or []:
                if a.name:
                    scene.add_actor(a.name, a.photo_url or '', a.gender or '')  # type: ignore[arg-type]
            for d in detail.directors or []:
                if d.name:
                    scene.add_director(d.name, d.photo_url or '')
            for pr in detail.producers or []:
                if pr.name:
                    scene.add_producer(pr.name, pr.photo_url or '')
            refs = [detail.art_referer] if detail.art_referer else []
            cks = [detail.art_cookie] if detail.art_cookie else []
            if await _resolve_and_fill(scene, fill_groups, studio=detail.studio or md.studio or '', site_name=site_name, referers=refs, cookies=cks):
                changed = True

    sources = PeopleManager()
    enqueued = False
    for entries, role, _key in groups:
        for r in entries:
            if r.thumb or not r.tag:
                continue
            if role == 'actor':
                sources.add_actor(r.tag, '', r.gender or '')  # type: ignore[arg-type]
            elif role == 'director':
                sources.add_director(r.tag, '')
            else:
                sources.add_producer(r.tag, '')
            enqueued = True
    if enqueued and await _resolve_and_fill(sources, fill_groups, studio=md.studio or '', site_name=site_name):
        changed = True

    logger.debug('meta-cache', f'backfill "{md.title}": changed={changed}')
    return changed


def backfill_metadata_attrs(response: PlexMetadataResponse) -> bool:
    from phoenixadult.registry import PROVIDER_DEFINITIONS
    from phoenixadult.utils.plex.rating_key import to_guid

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
        for attr in ('Role', 'Director', 'Producer'):
            roles: list[PlexRole] | None = getattr(md, attr)
            for idx, r in enumerate(roles or []):
                if r.order is None:
                    r.order = idx
                    changed = True
    return changed


def _recase_title(md: PlexMetadata, studio: str, scraper_type: str | None) -> bool:
    title = md.title
    if scraper_type == 'nubiles':
        from phoenixadult.clients.networks.nubiles import strip_episode_tag

        title = strip_episode_tag(title)
    cased_title = title_case(title, site_name=studio, scraper_type=scraper_type)
    if not cased_title or cased_title == md.title:
        return False
    md.title = cased_title
    md.titleSort = title_sort(cased_title)
    return True


def _normalize_summary(md: PlexMetadata) -> bool:
    if not md.summary:
        return False
    cleaned_summary = normalize_text(md.summary)
    if cleaned_summary == md.summary:
        return False
    md.summary = cleaned_summary
    return True


def _recase_studio_tagline(md: PlexMetadata, studio: str) -> bool:
    changed = False
    cased_studio = normalize_studio(studio)
    if cased_studio and cased_studio != md.studio:
        md.studio = cased_studio
        changed = True
    if md.tagline:
        cased_tagline = normalize_studio(md.tagline)
        if cased_tagline != md.tagline:
            md.tagline = cased_tagline
            changed = True
    if md.tagline and md.tagline == md.studio:
        md.tagline = None
        changed = True
    return changed


def _recase_collections(md: PlexMetadata) -> bool:
    if not md.Collection:
        return False
    tags = list(dict.fromkeys(normalize_studio(c.tag) for c in md.Collection if c.tag))
    if tags == [c.tag for c in md.Collection]:
        return False
    md.Collection = [PlexCollection(tag=t) for t in tags]
    return True


def _renormalize_genres(md: PlexMetadata, studio: str) -> bool:
    if not md.Genre:
        return False
    old = [g.tag for g in md.Genre]
    actors = tuple(r.tag for r in md.Role or [] if r.tag)
    new = normalize_genres(old, NormalizeGenresOptions(title=md.title, site_name=studio, actors=actors))
    if new == old:
        return False
    md.Genre = [PlexGenre(tag=t) for t in new]
    return True


def _realias_people(md: PlexMetadata, studio: str) -> bool:
    changed = False
    for attr in ('Role', 'Director', 'Producer'):
        roles: list[PlexRole] | None = getattr(md, attr)
        if not roles:
            continue
        seen: set[str] = set()
        kept: list[PlexRole] = []
        for r in roles:
            cased_name = re.sub(r'\s+', ' ', title_case(r.tag, type='name', site_name=studio)).strip()
            aliased = apply_name_aliases(cased_name, studio, studio)
            if aliased != r.tag:
                logger.info('meta-cache', f'recredited "{r.tag}" as "{aliased}"')
                r.tag = aliased
                if r.thumb and '/images/local/' in r.thumb:
                    r.thumb = None
                changed = True
            if aliased.lower() in seen:
                changed = True
                continue
            seen.add(aliased.lower())
            kept.append(r)
        if len(kept) != len(roles):
            setattr(md, attr, kept)
    return changed


def reapply_text_rules(response: PlexMetadataResponse, scraper_type: str | None = None) -> bool:
    changed = False
    for md in response.MediaContainer.Metadata:
        studio = md.studio or ''
        for field_changed in (
            _recase_title(md, studio, scraper_type),
            _normalize_summary(md),
            _recase_studio_tagline(md, studio),
            _recase_collections(md),
            _renormalize_genres(md, studio),
            _realias_people(md, studio),
        ):
            changed = field_changed or changed
    return changed
