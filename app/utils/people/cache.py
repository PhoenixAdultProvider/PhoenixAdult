from __future__ import annotations

import asyncio
import hashlib
import os
import re
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx2

from app.config import people_image_base
from app.config.env import env
from app.utils.fs.paths import safe_join
from app.utils.http.client import make_http
from app.utils.http.impersonate import impersonate_get_bytes
from app.utils.images import face_crop, face_crop_log
from app.utils.images.ext import IMAGE_EXTS
from app.utils.logging.logger import logger
from app.utils.people.generic import generic_image_url
from app.utils.people.types import Gender, Role, parse_person_filename


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


_ORIGINALS_DIR = 'originals'  # backing store of pre-crop originals (not a browsable role folder)


def _base_name(name: str, role: Role) -> str:
    return f'{role}.{_slug(name)}'


def _subdir(role: Role, gender: Gender) -> str:
    """On-disk subfolder for a person: 'directors' / 'producers', or for actors
    'actors/<male|female|trans|unknown>' (anything but male/female/trans is 'unknown')."""
    if role == 'actor':
        bucket = gender if gender in ('male', 'female', 'trans') else 'unknown'
        return f'actors/{bucket}'
    return f'{role}s'


def _subdir_for(filename: str) -> str:
    """The subfolder a cached filename belongs in, derived from its role+gender."""
    role, _, gender = parse_person_filename(filename)
    return _subdir(role, gender)  # type: ignore[arg-type]


_bust_cache: dict[str, tuple[float, str]] = {}


def _bust_token(relpath: str, data: bytes | None) -> str:
    if data is not None:
        return hashlib.sha1(data).hexdigest()[:8]  # noqa: S324 - cache-bust, not security
    path = safe_join(people_cache_dir(), relpath)
    if path is None:
        return ''
    try:
        mtime = path.stat().st_mtime
        hit = _bust_cache.get(relpath)
        if hit and hit[0] == mtime:
            return hit[1]
        token = hashlib.sha1(path.read_bytes()).hexdigest()[:8]  # noqa: S324 - cache-bust, not security
    except OSError:
        return ''
    _bust_cache[relpath] = (mtime, token)
    return token


def _local_url(relpath: str, data: bytes | None = None) -> str:
    """Served URL for a cached people image (relpath = '<subdir>/<filename>'), with a short
    content-hash cache-buster: Plex caches images by URL, so without a token a re-cropped or
    replaced image keeps serving the stale copy. The token changes only when the bytes do."""
    from urllib.parse import quote

    token = _bust_token(relpath, data)
    bust = f'?v={token}' if token else ''
    quoted = '/'.join(quote(part) for part in relpath.split('/'))
    return f'{people_image_base()}/images/local/{quoted}{bust}'


# ── Index (cache of cache contents) ───────────────────────────────────────────

_cached_dir: str | None = None
_cached_sig: tuple[int, float] | None = None
_cached_index: dict[str, str] = {}
_sig_checked_at = 0.0
_SIG_CHECK_INTERVAL = 30.0  # seconds between full-tree signature walks


def _served_files(root: Path) -> Iterator[Path]:
    """Cached served images across the role/gender subfolders — skips the originals/
    backing store, per-folder .face_crop_log.json, and non-images."""
    for entry in root.rglob('*'):
        if not entry.is_file() or entry.name.startswith('.') or entry.suffix.lower() not in IMAGE_EXTS:
            continue
        if entry.relative_to(root).parts[0] == _ORIGINALS_DIR:
            continue
        yield entry


def _dir_signature(directory: str) -> tuple[int, float]:
    count = 0
    mtime = 0.0
    root = Path(directory)
    if not root.exists():
        return count, mtime
    for entry in _served_files(root):
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
    root = Path(directory)
    if not root.exists():
        return idx
    for entry in _served_files(root):
        key = entry.stem.split('_', 1)[0]  # "actor.jane-doe"
        idx.setdefault(key, entry.relative_to(root).as_posix())  # "actors/female/actor.jane-doe_female.jpg"
    return idx


def _get_index() -> dict[str, str]:
    global _cached_dir, _cached_sig, _cached_index, _sig_checked_at
    directory = people_cache_dir()
    # The signature walk stats every headshot — rate-limit it; mutating paths
    # call _invalidate_index for an immediate rebuild.
    now = time.monotonic()
    if _cached_dir == directory and now - _sig_checked_at < _SIG_CHECK_INTERVAL:
        return _cached_index
    sig = _dir_signature(directory)
    _sig_checked_at = now
    if _cached_dir == directory and _cached_sig == sig:
        return _cached_index
    logger.info('people-cache', f'Rebuilding Local Actor Image Index ({directory})')
    _cached_index = _rebuild_index(directory)
    _cached_dir = directory
    _cached_sig = sig
    return _cached_index


def _invalidate_index() -> None:
    global _cached_dir, _cached_sig, _sig_checked_at
    _cached_dir = None
    _cached_sig = None
    _sig_checked_at = 0.0


# ── Public ─────────────────────────────────────────────────────────────────────


def lookup_cached(name: str, role: Role) -> dict[str, str] | None:
    if not cache_enabled():
        return None
    key = _base_name(name, role)
    relpath = _get_index().get(key)
    if not relpath:
        return None
    gender = parse_person_filename(Path(relpath).name)[2]
    return {'served_url': _local_url(relpath), 'gender': gender}


def _ext_for(content_type: str, upstream_url: str) -> str:
    from_ct = content_type.split('/')[1].split(';')[0].lower() if '/' in content_type else ''
    ext = f'.{"jpg" if from_ct == "jpeg" else from_ct}' if from_ct else ''
    if not ext or ext not in IMAGE_EXTS:
        tail = upstream_url.split('.')[-1].split('?')[0].lower() if '.' in upstream_url else ''
        ext = f'.{tail}'
    return ext if ext in IMAGE_EXTS else ''


async def _download_image(url: str, headers: dict[str, str] | None) -> tuple[bytes, str] | None:
    """Image bytes for the cache. Plain client first; fall back to curl_cffi
    impersonation for Cloudflare-gated hosts (e.g. IAFD headshots 403 a plain GET)."""
    try:
        async with make_http() as client:
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


async def cache_photo(
    upstream_url: str, name: str, role: Role, gender: Gender, headers: dict[str, str] | None = None, source: str = ''
) -> dict[str, str] | None:
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

    # Optional face-crop (tight head crop for Plex's circular card). Never crops the
    # generic/default placeholder; runs off-thread; the cropper emits JPEG and
    # returns None to mean "keep the original".
    orig_ext = ext
    original = data  # pre-crop bytes, preserved so the user can always go back
    face_on = env.people_cache_face_enabled and not _is_generic(upstream_url) and source not in _NO_CROP_SOURCES
    cropped = False
    if face_on:
        out = await asyncio.to_thread(face_crop.crop_to_headshot, data)
        if out is not None:
            data, ext, cropped = out, '.jpg', True

    base = _base_name(name, role)
    name_base = f'{base}_{gender}' if gender else base
    filename = f'{name_base}{ext}'
    subdir = _subdir(role, gender)
    relpath = f'{subdir}/{filename}'
    # Defense in depth: never write outside the cache dir even if _slug misses.
    filepath = safe_join(directory, subdir, filename)
    if filepath is None:
        logger.warn('people-cache', f'refusing to write outside cache dir: {relpath}')
        return None
    # Preserve the pre-crop original so "Use original" can restore it offline. Only when we
    # actually cropped — an uncropped served file already IS the original.
    orig_path = safe_join(directory, _ORIGINALS_DIR, f'{name_base}{orig_ext}') if cropped else None

    def _write() -> None:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_bytes(data)
        if orig_path is not None:
            orig_path.parent.mkdir(parents=True, exist_ok=True)
            orig_path.write_bytes(original)
        # Always record (not just for crops) so every cached image keeps its upstream URL.
        face_crop_log.record(str(filepath.parent), name=name, filename=filename, base=name_base, orig_ext=orig_ext, upstream_url=upstream_url, cropped=cropped)

    await asyncio.to_thread(_write)
    _invalidate_index()
    logger.info('people-cache', f'cached {relpath}{" (face-cropped)" if cropped else ""}')
    return {'served_url': _local_url(relpath, data), 'gender': gender}


# Sources whose images are already tight headshots — cropping again only degrades them.
_NO_CROP_SOURCES = {'IAFD'}


def _is_generic(url: str) -> bool:
    # The silhouette placeholder IS cached (speeds future lookups) but must never be
    # face-cropped — a generic head would crop to garbage.
    return bool(url) and url in {generic_image_url('female'), generic_image_url('male')}


def _log_entry(subdir_path: str, filename: str) -> dict[str, Any] | None:
    return next((e for e in face_crop_log.recent(subdir_path) if e.get('filename') == filename), None)


async def restore_original(filename: str) -> bool:
    """Replace a cropped cache file with its un-cropped original. Prefers the preserved
    local original (offline-safe); falls back to re-downloading the upstream. Backs the
    /people-cache 'Use original' action."""
    directory = people_cache_dir()
    subdir = _subdir_for(filename)
    subdir_path = safe_join(directory, subdir)
    if subdir_path is None:
        return False
    entry = _log_entry(str(subdir_path), filename)
    if not entry:
        return False
    orig_ext = entry.get('orig_ext') or '.jpg'

    local = safe_join(directory, _ORIGINALS_DIR, f'{entry["base"]}{orig_ext}')
    data: bytes | None = local.read_bytes() if local is not None and local.exists() else None
    if data is None and entry.get('upstream_url'):
        # IAFD headshots are Cloudflare-403'd — _download_image falls back to impersonation.
        fetched = await _download_image(entry['upstream_url'], None)
        data = fetched[0] if fetched else None
    if data is None:
        logger.warn('people-cache', f'restore failed for {filename} (no local original or upstream)')
        return False

    target_name = f'{entry["base"]}{orig_ext}'
    target = safe_join(directory, subdir, target_name)
    if target is None:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    if target_name != filename:
        old = safe_join(directory, subdir, filename)
        if old is not None and old != target and old.exists():
            old.unlink()
    _invalidate_index()
    face_crop_log.update(str(subdir_path), filename, filename=target_name, cropped=False)
    logger.info('people-cache', f'restored original for {subdir}/{target_name}')
    return True


def purge(filename: str) -> bool:
    """Delete a cached image (and its preserved original) and drop its crop-log entry.
    Backs the /people-cache 'Purge' button."""
    directory = people_cache_dir()
    subdir = _subdir_for(filename)
    target = safe_join(directory, subdir, filename)  # path-traversal guard
    if target is None or not target.exists():
        return False
    try:
        target.unlink()
    except OSError as err:
        logger.warn('people-cache', f'purge failed {filename}: {err}')
        return False
    entry = _log_entry(str(target.parent), filename)
    if entry:
        orig = safe_join(directory, _ORIGINALS_DIR, f'{entry["base"]}{entry.get("orig_ext") or ".jpg"}')
        if orig is not None and orig.exists():
            orig.unlink()
    _invalidate_index()
    face_crop_log.remove(str(target.parent), filename)
    logger.info('people-cache', f'purged {subdir}/{filename}')
    return True


_GENDERS = ('', 'male', 'female', 'trans')


def set_gender(filename: str, new_gender: str) -> str | None:
    """Correct a cached actor's gender: rename the `_<gender>` suffix, MOVE the file to the
    matching actors/<gender> folder (directors/producers stay put), move the preserved
    original and crop-log entry, and refresh the index. Returns the new filename."""
    if new_gender not in _GENDERS:
        return None
    directory = people_cache_dir()
    role, slug, old_gender = parse_person_filename(filename)  # role.slug[_gender]
    root = f'{role}.{slug}' if role else slug  # gender-less role.slug
    if not root:
        return None
    ext = Path(filename).suffix
    new_base = f'{root}_{new_gender}' if new_gender else root
    new_filename = f'{new_base}{ext}'
    old_subdir, new_subdir = _subdir(role, old_gender), _subdir(role, new_gender)  # type: ignore[arg-type]

    src = safe_join(directory, old_subdir, filename)
    dst = safe_join(directory, new_subdir, new_filename)
    if src is None or dst is None:
        return None  # path-traversal guard
    if dst != src:
        if not src.exists():
            return None
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            dst.unlink()
        src.rename(dst)

    old_log, new_log = str(src.parent), str(dst.parent)
    entry = _log_entry(old_log, filename)
    if entry:
        orig_ext = entry.get('orig_ext') or '.jpg'
        old_orig = safe_join(directory, _ORIGINALS_DIR, f'{entry["base"]}{orig_ext}')
        new_orig = safe_join(directory, _ORIGINALS_DIR, f'{new_base}{orig_ext}')
        if old_orig is not None and new_orig is not None and old_orig != new_orig and old_orig.exists():
            if new_orig.exists():
                new_orig.unlink()
            old_orig.rename(new_orig)
    if old_subdir != new_subdir:
        face_crop_log.remove(old_log, filename)
        if entry:
            face_crop_log.record(
                new_log,
                name=entry.get('name', ''),
                filename=new_filename,
                base=new_base,
                orig_ext=entry.get('orig_ext') or '.jpg',
                upstream_url=entry.get('upstream_url', ''),
                cropped=bool(entry.get('cropped')),
            )
    else:
        face_crop_log.update(old_log, filename, filename=new_filename, base=new_base)
    _invalidate_index()
    logger.info('people-cache', f'gender set to "{new_gender or "none"}" -> {new_subdir}/{new_filename}')
    return new_filename
