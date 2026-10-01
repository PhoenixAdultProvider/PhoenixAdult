from __future__ import annotations

import asyncio
import json
import re
import shutil
import sqlite3
import weakref
from pathlib import Path
from typing import Any, Literal

import httpx2
from PIL import Image as PILImage

from phoenixadult.config import config, image_base_url
from phoenixadult.config.env import env
from phoenixadult.models.metadata import PlexCollection, PlexCountry, PlexData18, PlexGenre, PlexImage, PlexMetadata, PlexMetadataResponse, PlexRole
from phoenixadult.registry import find_site
from phoenixadult.utils.auth.url_signing import sign_url, strip_sig
from phoenixadult.utils.cache import scene_store
from phoenixadult.utils.cache.layout import BUNDLE_FILE, bundle_path, bundle_payload, cache_dir, enabled, scene_hash_for
from phoenixadult.utils.cache.locks import apply_locks, carry_emptied_fields, changed_lockables, lock_snapshot, reconcile_dropped_images
from phoenixadult.utils.concurrency import gate
from phoenixadult.utils.concurrency.gate import loop_gate
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.fs.paths import safe_join
from phoenixadult.utils.helpers.data18 import data18_ref_with_extras, manual_mapping_url, mapping_slug
from phoenixadult.utils.images.ext import ext_from
from phoenixadult.utils.images.image_fetcher import fetch_image, is_solid, rotate_image_bytes
from phoenixadult.utils.images.proxy import proxy_params
from phoenixadult.utils.logging.logger import logger

_ERROR_TITLE_RE = re.compile(r'\b(404|403|401|500|not found|forbidden|access denied|just a moment|attention required|page not found|error)\b', re.IGNORECASE)


def _image_gate() -> asyncio.Semaphore:
    return loop_gate('image-fetch', gate.IMAGE_FETCH)


_write_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()


# ── Data18 Manual-Mapping Change Detection ────────────────────────────────────


def _data18_fingerprint(response: PlexMetadataResponse) -> str:

    try:
        md = response.MediaContainer.Metadata[0]
    except (AttributeError, IndexError):
        return ''
    return manual_mapping_url(mapping_slug(md.title or '', md.tagline or md.studio)) or ''


def _stored_data18(response: PlexMetadataResponse) -> dict[str, Any] | None:
    try:
        d = response.MediaContainer.Metadata[0].data18
    except (AttributeError, IndexError):
        return None
    if not d:
        return None
    stored: dict[str, Any] = {'type': d.type, 'id': d.id}
    if d.also:
        stored['also'] = list(d.also)
    return stored


def data18_remap_needed(response: PlexMetadataResponse, site_name: str) -> bool:

    if not env.data18_enabled:
        return False
    site = find_site(site_name)
    if not site or not site.scraper_config.data18_enrichment:
        return False
    manual = data18_ref_with_extras(_data18_fingerprint(response))
    return manual is not None and manual != _stored_data18(response)


def data18_backfill_needed(response: PlexMetadataResponse, site_name: str) -> bool:
    if not env.data18_enabled:
        return False
    site = find_site(site_name)
    if not site or not site.scraper_config.data18_enrichment:
        return False
    return any(md.data18 is None and md.title for md in response.MediaContainer.Metadata)


# ── Read ─────────────────────────────────────────────────────────────────────


def read(site_name: str, cur_id: str) -> dict[str, Any] | None:
    if not enabled():
        return None
    loaded = scene_store.load(scene_hash_for(site_name, cur_id))
    if loaded is None:
        return None
    rebased = _rebase(loaded, config.base_url.rstrip('/'), image_base_url().rstrip('/'))
    return rebased if isinstance(rebased, dict) else None


# ── Write ────────────────────────────────────────────────────────────────────

_SNAPSHOT_IMG_RE = re.compile(r'^/cache/(?P<rel>.+)/images/(?P<name>[^/?#]+)$')


def _snapshot_file(url: str, base: str) -> tuple[Path, str] | None:
    path = strip_sig(url[len(base) :] if url.startswith(f'{base}/') else url)
    match = _SNAPSHOT_IMG_RE.match(path)
    if match is None:
        return None
    target = safe_join(cache_dir(), f'{match["rel"]}/images/{match["name"]}')
    return None if target is None else (target, match['name'])


def _probe_file(path: Path) -> tuple[tuple[int, int, int], bool] | None:
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
            return sign_url(f'{people_base}{obj[obj.index(marker) :]}')
        if obj.startswith('/cache/') or obj.startswith('/images/'):
            return sign_url(f'{base}{obj}')
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

    scene_hash = scene_hash_for(site_name, cur_id)
    rel_path = bundle_path(scene_hash)
    final_dir = safe_join(cache_dir(), rel_path)
    if final_dir is None:
        return False

    lock = _write_locks.get(scene_hash)
    if lock is None:
        lock = asyncio.Lock()
        _write_locks[scene_hash] = lock
    async with lock:
        return await _SnapshotWrite(response, site_name, cur_id, scene_hash, rel_path, final_dir, allow_clear).run()


class _SnapshotWrite:
    def __init__(self, response: PlexMetadataResponse, site_name: str, cur_id: str, scene_hash: str, rel_path: str, final_dir: Path, allow_clear: bool) -> None:
        self.site_name = site_name
        self.cur_id = cur_id
        self.scene_hash = scene_hash
        self.rel_path = rel_path
        self.final_dir = final_dir
        self.allow_clear = allow_clear
        self.tmp_dir = final_dir.parent / f'{scene_hash}.tmp'
        self.data = response.model_dump(by_alias=True, exclude_none=True)
        self.meta: dict[str, Any] = self.data['MediaContainer']['Metadata'][0]
        self.base = config.base_url.rstrip('/')
        self.counter = 0
        self.image_meta: dict[str, tuple[int, int, int]] = {}
        self.rotations: dict[str, int] = {}
        self.kept_names: set[str] = set()

    async def run(self) -> bool:
        if not self.allow_clear:
            await self._hold_stored_values()
        self._take_rotations()
        await run_in('fs', self._reset_tmp)
        try:
            await self._stage_images()
            await run_in('fs', self._write_bundle)
            await run_in('fs', self._promote)
        except OSError as err:
            await run_in('fs', shutil.rmtree, self.tmp_dir, ignore_errors=True)
            logger.warn('meta-cache', f'snapshot write failed {self.rel_path}: {err}')
            return False
        return await self._index()

    # ── Carry and Locks ───────────────────────────────────────────────────────

    async def _hold_stored_values(self) -> None:
        previous = await run_in('store', scene_store.load, self.scene_hash)
        if carried := carry_emptied_fields(self.meta, previous):
            logger.warn('meta-cache', f'scrape returned nothing for {", ".join(carried)} on {self.rel_path} — kept the stored values')
        locks = await run_in('store', scene_store.locks, self.scene_hash)
        if held := apply_locks(self.meta, previous, locks):
            logger.info('meta-cache', f'locks held {", ".join(held)} on {self.rel_path} — the scrape does not overwrite them')

    def _take_rotations(self) -> None:
        for img in self.meta.get('Image') or []:
            turn = int(img.pop('rotate', 0) or 0) % 360
            if turn and img.get('url'):
                self.rotations[str(img['url'])] = turn

    def _reset_tmp(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    # ── Stage Images ──────────────────────────────────────────────────────────

    def _targets(self) -> list[tuple[dict[str, Any], str, str]]:
        meta = self.meta
        found: list[tuple[dict[str, Any], str, str]] = [(meta, 'thumb', 'poster'), (meta, 'art', 'art')]
        found.extend((img, 'url', 'img') for img in meta.get('Image', []))
        for role_key in ('Role', 'Director', 'Producer', 'Writer'):
            found.extend((role, 'thumb', 'role') for role in meta.get(role_key, []))
        found.extend((rating, 'image', 'rating') for rating in meta.get('Rating', []))
        return [(obj, key, hint) for obj, key, hint in found if obj.get(key)]

    def _relativize(self, u: str) -> str:
        u = strip_sig(u)
        return u[len(self.base) :] if u.startswith(f'{self.base}/') else u

    def _keep(self, source: Path, name: str, turn: int = 0) -> tuple[str, tuple[int, int, int] | None, bool] | None:
        if not source.is_file():
            return None
        img_dir = self.tmp_dir / 'images'
        img_dir.mkdir(exist_ok=True)
        copied = img_dir / name
        shutil.copy2(source, copied)
        if turn:
            copied.write_bytes(rotate_image_bytes(copied.read_bytes(), turn))
        probed = _probe_file(copied)
        if probed is not None and probed[1]:
            copied.unlink(missing_ok=True)
            return f'/cache/{self.rel_path}/images/{name}', None, True
        return f'/cache/{self.rel_path}/images/{name}', (probed[0] if probed else None), False

    def _store_bytes(self, name: str, payload: bytes) -> None:
        img_dir = self.tmp_dir / 'images'
        img_dir.mkdir(exist_ok=True)
        (img_dir / name).write_bytes(payload)

    async def _localize(self, url: str | None, hint: str, sem: asyncio.Semaphore) -> str | None:
        if not url:
            return url
        if '/images/local/' in url:
            return strip_sig(url[url.index('/images/local/') :])
        if (hit := _snapshot_file(url, self.base)) is not None:
            if (kept := await run_in('fs', self._keep, *hit, self.rotations.get(url, 0))) is not None:
                local, probed, solid = kept
                if solid:
                    logger.info('meta-cache', f'dropped a solid-color image from {self.rel_path}: {hit[1]}')
                    return None
                if probed:
                    self.image_meta[local] = probed
                return local
            logger.info('meta-cache', f'dropped {url} from {self.rel_path}: the snapshot image it points at is gone from disk')
            return None
        target, referers, cookies = proxy_params(url)
        while (name := f'{hint}-{self.counter:02d}{ext_from("", target)}') in self.kept_names:
            self.counter += 1
        self.counter += 1
        try:
            async with sem:
                entry = await fetch_image(target, referers or None, cookies or None)
            if entry.solid:
                logger.info('meta-cache', f'skipped a solid-color image for {self.rel_path}: {target}')
                return None
            payload, width, height = entry.data, entry.width, entry.height
            if turn := self.rotations.get(url, 0):
                payload = rotate_image_bytes(payload, turn)
                if turn in (90, 270):
                    width, height = height, width
            await run_in('fs', self._store_bytes, name, payload)
            local = f'/cache/{self.rel_path}/images/{name}'
            self.image_meta[local] = (width, height, len(payload))
            return local
        except (httpx2.HTTPError, ValueError, OSError) as err:
            logger.debug('meta-cache', f'image download failed {target}: {err!r}')
            return self._relativize(url)

    async def _stage_images(self) -> None:
        sem = _image_gate()
        targets = self._targets()
        self.kept_names = {hit[1] for obj, key, _hint in targets if (hit := _snapshot_file(str(obj[key]), self.base)) is not None}

        by_url: dict[str, list[tuple[dict[str, Any], str]]] = {}
        hints: dict[str, str] = {}
        for obj, key, hint in targets:
            url = str(obj[key])
            by_url.setdefault(url, []).append((obj, key))
            hints.setdefault(url, hint)

        async def _assign(url: str, holders: list[tuple[dict[str, Any], str]]) -> None:
            resolved = await self._localize(url, hints[url], sem)
            for obj, key in holders:
                obj[key] = resolved

        await asyncio.gather(*(_assign(url, holders) for url, holders in by_url.items()))
        reconcile_dropped_images(self.meta, self.image_meta)

    # ── Write Bundle and Promote ──────────────────────────────────────────────

    def _write_bundle(self) -> None:
        payload = bundle_payload(self.site_name, self.cur_id, self.scene_hash, self.data, self.image_meta)
        (self.tmp_dir / BUNDLE_FILE).write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')

    def _promote(self) -> None:
        if self.final_dir.exists():
            shutil.rmtree(self.final_dir, ignore_errors=True)
        self.tmp_dir.rename(self.final_dir)

    # ── Index ─────────────────────────────────────────────────────────────────

    async def _index(self) -> bool:
        try:
            await run_in('store', scene_store.upsert, self.site_name, self.cur_id, self.scene_hash, self.rel_path, self.data, self.image_meta)
        except sqlite3.Error as err:
            logger.warn('meta-cache', f'snapshot db write failed {self.rel_path}: {err}')
            return False
        logger.info('meta-cache', f'snapshot saved {self.rel_path} ({self.meta.get("title", "")})')
        return True


# ── Management (UI) ──────────────────────────────────────────────────────────


_EDITABLE_TAGS = {'Genre': PlexGenre, 'Collection': PlexCollection, 'Country': PlexCountry}
_EDITABLE_ROLES = ('Role', 'Director', 'Producer')


def drop_stale_people_thumbs(response: PlexMetadataResponse, site_name: str, cur_id: str) -> bool:
    if not scene_store.take_force_refresh(scene_hash_for(site_name, cur_id)):
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
    ids = [p for p in re.split(r'[\s,]+', str(fields['data18_id'] or '').strip()) if p]
    if not ids:
        md.data18 = None
        return
    primary, extras = ids[0], ids[1:]
    raw_type = str(fields.get('data18_type') or '').strip() or (md.data18.type if md.data18 else '')
    kind: Literal['scene', 'movie'] = 'movie' if raw_type == 'movie' else 'scene'
    if md.data18 and md.data18.id == primary and md.data18.type == kind and (md.data18.also or []) == extras:
        return
    md.data18 = PlexData18(type=kind, id=primary, manual=True, also=extras or None)


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
        prior_urls = {i.url for i in md.Image or []}
        images = [
            PlexImage(
                url=str(i.get('url', '')).strip(),
                type=str(i.get('type', '')).strip() or 'coverPoster',
                priority=True if i.get('priority') else None,
                rotate=r if (r := int(i.get('rotate') or 0) % 360) in (90, 180, 270) else None,
                locked=True if i.get('locked') or (r in (90, 180, 270)) or str(i.get('url', '')).strip() not in prior_urls else None,
            )
            for i in fields['Image'] or []
        ]
        md.Image = [i for i in images if i.url] or None
        md.thumb = next((i.url for i in md.Image or [] if i.type == 'coverPoster'), None)
        md.art = next((i.url for i in md.Image or [] if i.type == 'background'), None)


async def save_edits(key: str, fields: dict[str, Any]) -> str | None:
    identity, loaded = await run_in('store', lambda: (scene_store.identity_for(key), load_for_edit(key)))
    if identity is None or loaded is None:
        return None
    site_name, cur_id = identity
    response = PlexMetadataResponse.model_validate(loaded)
    try:
        md = response.MediaContainer.Metadata[0]
    except (AttributeError, IndexError):
        return None
    before = lock_snapshot(md)
    _apply_edits(md, fields)
    if not await write(site_name, cur_id, response, allow_clear=True):
        return None
    scene_hash = scene_hash_for(site_name, cur_id)
    current = await run_in('store', scene_store.locks, scene_hash)
    requested = fields.get('lockedFields')
    base = {str(f) for f in requested if isinstance(f, str)} if isinstance(requested, list) else set(current['fields'])
    auto = changed_lockables(before, lock_snapshot(md))
    images_locked = bool(fields['imagesLocked']) if 'imagesLocked' in fields else bool(current['imagesLocked'])
    await run_in('store', scene_store.set_locks, scene_hash, sorted(base | auto), images_locked)
    return bundle_path(scene_hash)
