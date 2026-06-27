from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

import httpx2

from app.config import config
from app.config.env import env
from app.utils.http.impersonate import impersonate_get_bytes
from app.utils.images import face_crop, face_crop_log
from app.utils.logging.logger import logger
from app.utils.people.generic import generic_image_url
from app.utils.people.types import Gender, Role

_VALID_EXT = {'.jpg', '.jpeg', '.png', '.webp', '.tbn', '.jfif'}


def people_cache_dir() -> str:
    return env.people_cache_dir


def cache_enabled() -> bool:
    return env.people_cache_enabled


def cache_replace_enabled() -> bool:
    return env.people_cache_replace_enabled


def _slug(name: str) -> str:
    # A scraped name becomes part of the on-disk filename — strip path separators
    # and collapse `..` so a crafted name can't escape the cache dir.
    return re.sub(r'\s+', '-', re.sub(r'\.{2,}', '.', re.sub(r'[/\\]', '-', name))).lower()


def _base_name(name: str, role: Role) -> str:
    return f'{role}.{_slug(name)}'


# ── Index (cache of cache contents) ───────────────────────────────────────────

_cached_dir: str | None = None
_cached_sig: tuple[int, float] | None = None
_cached_index: dict[str, str] = {}


def _dir_signature(directory: str) -> tuple[int, float]:
    count = 0
    mtime = 0.0
    p = Path(directory)
    if not p.exists():
        return count, mtime
    for entry in p.iterdir():
        if not entry.is_file():
            continue
        count += 1
        try:
            m = entry.stat().st_mtime
            if m > mtime:
                mtime = m
        except OSError:
            pass
    return count, mtime


def _rebuild_index(directory: str) -> dict[str, str]:
    idx: dict[str, str] = {}
    p = Path(directory)
    if not p.exists():
        return idx
    for entry in p.iterdir():
        base = entry.stem  # e.g. "actor.jane-doe_female"
        key = base.split('_', 1)[0]  # "actor.jane-doe"
        idx.setdefault(key, entry.name)
    return idx


def _get_index() -> dict[str, str]:
    global _cached_dir, _cached_sig, _cached_index
    directory = people_cache_dir()
    sig = _dir_signature(directory)
    if _cached_dir == directory and _cached_sig == sig:
        return _cached_index
    logger.info('people-cache', f'Rebuilding Local Actor Image Index ({directory})')
    _cached_index = _rebuild_index(directory)
    _cached_dir = directory
    _cached_sig = sig
    return _cached_index


def _invalidate_index() -> None:
    global _cached_dir, _cached_sig
    _cached_dir = None
    _cached_sig = None


# ── Public ─────────────────────────────────────────────────────────────────────


def lookup_cached(name: str, role: Role) -> dict[str, str] | None:
    if not cache_enabled():
        return None
    key = _base_name(name, role)
    filename = _get_index().get(key)
    if not filename:
        return None
    parsed = Path(filename).stem
    tail = parsed.split('_')[-1] if '_' in parsed else ''
    gender: Gender = tail if tail in ('male', 'female', 'trans') else ''  # type: ignore[assignment]
    from urllib.parse import quote

    return {'served_url': f'{config.base_url}/images/local/{quote(filename)}', 'gender': gender}


def _ext_for(content_type: str, upstream_url: str) -> str:
    from_ct = content_type.split('/')[1].split(';')[0].lower() if '/' in content_type else ''
    ext = f'.{"jpg" if from_ct == "jpeg" else from_ct}' if from_ct else ''
    if not ext or ext not in _VALID_EXT:
        tail = upstream_url.split('.')[-1].split('?')[0].lower() if '.' in upstream_url else ''
        ext = f'.{tail}'
    return ext if ext in _VALID_EXT else ''


async def _download_image(url: str, headers: dict[str, str] | None) -> tuple[bytes, str] | None:
    """Image bytes for the cache. Plain client first; fall back to curl_cffi
    impersonation for Cloudflare-gated hosts (e.g. IAFD headshots 403 a plain GET)."""
    try:
        async with httpx2.AsyncClient(timeout=15.0, verify=False, follow_redirects=True) as client:
            resp = await client.get(url, headers={'User-Agent': 'Mozilla/5.0', **(headers or {})})
            resp.raise_for_status()
            content_type = resp.headers.get('content-type', 'image/jpeg')
            if content_type.lower().startswith('image/'):
                return resp.content, content_type
            logger.debug('people-cache', f'plain fetch returned non-image ({content_type}) for {url}; trying impersonate')
    except (httpx2.HTTPError, OSError) as err:
        logger.debug('people-cache', f'plain fetch failed {url}: {err}; trying impersonate')
    # NB: don't pass a User-Agent — curl_cffi must keep its impersonated UA, or the
    # UA/TLS-fingerprint mismatch gets Cloudflare-403'd (e.g. IAFD headshots).
    got = await impersonate_get_bytes(url, headers)
    if got:
        logger.debug('people-cache', f'impersonate fetched {url}')
        return got
    logger.warn('people-cache', f'fetch failed {url} (plain + impersonate)')
    return None


async def cache_photo(upstream_url: str, name: str, role: Role, gender: Gender, headers: dict[str, str] | None = None) -> dict[str, str] | None:
    if not cache_enabled():
        return None
    directory = people_cache_dir()
    os.makedirs(directory, exist_ok=True)

    if not cache_replace_enabled():
        existing = lookup_cached(name, role)
        if existing:
            return existing

    fetched = await _download_image(upstream_url, headers)
    if not fetched:
        return None
    data, content_type = fetched

    if len(data) > 20 * 1024 * 1024:
        logger.warn('people-cache', f'image too large {upstream_url}')
        return None

    ext = _ext_for(content_type, upstream_url)
    if not ext:
        logger.warn('people-cache', f'invalid extension for {upstream_url} (content-type={content_type})')
        return None

    # Optional face-crop (head+shoulders for Plex's circular card). Never crops the
    # generic/default placeholder; runs off-thread; the cropper emits JPEG and
    # returns None to mean "keep the original".
    orig_ext = ext
    face_on = env.people_cache_face_enabled and not _is_generic(upstream_url)
    cropped = False
    if face_on:
        out = await asyncio.to_thread(face_crop.crop_to_headshot, data)
        if out is not None:
            data, ext, cropped = out, '.jpg', True

    base = _base_name(name, role)
    name_base = f'{base}_{gender}' if gender else base
    filename = f'{name_base}{ext}'
    root = Path(directory).resolve()
    filepath = (root / filename).resolve()
    # Defense in depth: never write outside the cache dir even if _slug misses.
    if filepath != root and root not in filepath.parents:
        logger.warn('people-cache', f'refusing to write outside cache dir: {filename}')
        return None

    filepath.write_bytes(data)
    _invalidate_index()
    logger.info('people-cache', f'cached {filename}{" (face-cropped)" if cropped else ""}')
    if face_on:
        face_crop_log.record(directory, name=name, filename=filename, base=name_base, orig_ext=orig_ext, upstream_url=upstream_url, cropped=cropped)
    from urllib.parse import quote

    return {'served_url': f'{config.base_url}/images/local/{quote(filename)}', 'gender': gender}


def _is_generic(url: str) -> bool:
    # The generic/default placeholder is served as a raw URL and normally never
    # reaches the cache; guard anyway so it's never face-cropped.
    return bool(url) and url in {generic_image_url('female'), generic_image_url('male')}


async def restore_original(filename: str) -> bool:
    """Re-fetch an image's upstream original and write it UNCROPPED, replacing the
    cropped cache file. Backs the /people-cache 'use original' action."""
    directory = people_cache_dir()
    entry = next((e for e in face_crop_log.recent(directory) if e.get('filename') == filename), None)
    if not entry:
        return False
    try:
        async with httpx2.AsyncClient(timeout=15.0, verify=False, follow_redirects=True) as client:
            resp = await client.get(entry['upstream_url'], headers={'User-Agent': 'Mozilla/5.0'})
            resp.raise_for_status()
            data = resp.content
    except (httpx2.HTTPError, OSError) as err:
        logger.warn('people-cache', f'restore fetch failed {entry["upstream_url"]}: {err}')
        return False

    root = Path(directory).resolve()
    target_name = f'{entry["base"]}{entry.get("orig_ext") or ".jpg"}'
    target = (root / target_name).resolve()
    if target != root and root not in target.parents:
        return False
    target.write_bytes(data)
    if target_name != filename:
        old = (root / filename).resolve()
        if old != target and root in old.parents and old.exists():
            old.unlink()
    _invalidate_index()
    face_crop_log.update(directory, filename, filename=target_name, cropped=False)
    logger.info('people-cache', f'restored original for {target_name}')
    return True


_GENDERS = ('', 'male', 'female')


def set_gender(filename: str, new_gender: str) -> str | None:
    """Correct a cached image's gender by renaming its `_<gender>` suffix and
    refreshing the lookup index. Returns the new filename, or None on failure.
    The gender lives in the filename, so a rename is all future lookups (and the
    served URL) need to report the corrected gender."""
    if new_gender not in _GENDERS:
        return None
    directory = people_cache_dir()
    stem = Path(filename).stem  # role.slug[_gender] — parse the base off the name, not the crop log
    head, _, tail = stem.rpartition('_')
    root = head if (tail in ('male', 'female', 'trans') and head) else stem  # gender-less role.slug
    if not root:
        return None
    ext = Path(filename).suffix
    new_base = f'{root}_{new_gender}' if new_gender else root
    new_filename = f'{new_base}{ext}'

    root_dir = Path(directory).resolve()
    src = (root_dir / filename).resolve()
    dst = (root_dir / new_filename).resolve()
    if root_dir not in src.parents or root_dir not in dst.parents:
        return None  # path-traversal guard
    if new_filename != filename:
        if not src.exists():
            return None
        if dst.exists() and dst != src:
            dst.unlink()
        src.rename(dst)
    _invalidate_index()
    face_crop_log.update(directory, filename, filename=new_filename, base=new_base)
    logger.info('people-cache', f'gender set to "{new_gender or "none"}" -> {new_filename}')
    return new_filename
