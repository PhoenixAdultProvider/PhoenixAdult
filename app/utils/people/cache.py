from __future__ import annotations

import asyncio
import hashlib
import os
import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx2

from app.config import people_image_base
from app.config.env import env
from app.utils import db
from app.utils.fs.paths import safe_join
from app.utils.http.client import make_http
from app.utils.http.impersonate import impersonate_get_bytes
from app.utils.images import face_crop, face_crop_log
from app.utils.images.ext import IMAGE_EXTS, ext_from, is_image_content_type
from app.utils.logging.logger import logger
from app.utils.people.generic import generic_image_url
from app.utils.people.types import Gender, PersonType, parse_person_filename


def people_cache_dir() -> str:
    return env.people_cache_dir


def cache_enabled() -> bool:
    return env.people_cache_enabled


def cache_replace_enabled() -> bool:
    return env.people_cache_replace_enabled


def _slug(name: str) -> str:
    """Filename-safe slug: strips path separators and collapses `..` so a crafted name can't escape the cache dir."""
    return re.sub(r'\s+', '-', re.sub(r'\.{2,}', '.', re.sub(r'[/\\]', '-', name))).lower()


_ORIGINALS_DIR = 'originals'


def _base_name(name: str, type: PersonType) -> str:
    return f'{type}.{_slug(name)}'


def _subdir(type: PersonType, gender: Gender) -> str:
    """On-disk subfolder for a person: 'directors' / 'producers', or for actors
    'actors/<male|female|trans|unknown>' (anything but male/female/trans is 'unknown')."""
    if type == 'actor':
        bucket = gender if gender in ('male', 'female', 'trans') else 'unknown'
        return f'actors/{bucket}'
    return f'{type}s'


def _subdir_for(filename: str) -> str:
    """The subfolder a cached filename belongs in, derived from its type+gender."""
    type, _, gender = parse_person_filename(filename)
    return _subdir(type, gender)  # type: ignore[arg-type]


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
    """Served URL for a cached people image (relpath = '<subdir>/<filename>') with a content-hash
    cache-buster: Plex caches images by URL, so the token changes only when the bytes do."""
    from urllib.parse import quote

    token = _bust_token(relpath, data)
    bust = f'?v={token}' if token else ''
    quoted = '/'.join(quote(part) for part in relpath.split('/'))
    return f'{people_image_base()}/images/local/{quoted}{bust}'


# ── Index (people_images table; files are the source of truth) ────────────────


_index = db.ReconciledConn(people_cache_dir, lambda: _rebuild_index(db.connect()))


def _served_files(root: Path) -> Iterator[Path]:
    """Cached served images across the type/gender subfolders — skips the originals/
    backing store, hidden files, and non-images."""
    for entry in root.rglob('*'):
        if not entry.is_file() or entry.name.startswith('.') or entry.suffix.lower() not in IMAGE_EXTS:
            continue
        if entry.relative_to(root).parts[0] == _ORIGINALS_DIR:
            continue
        yield entry


def reconcile() -> None:
    """Rebuild the people_images index from the files on disk."""
    _index.reconcile()


def _index_conn() -> sqlite3.Connection:
    return _index.connect()


def _rebuild_index(conn: sqlite3.Connection) -> None:
    root = Path(people_cache_dir())
    rows: list[tuple[str, str, str, str, str, float]] = []
    if root.exists():
        for entry in sorted(_served_files(root)):
            type, slug, gender = parse_person_filename(entry.name)
            if not type or not slug:
                continue
            try:
                mtime = entry.stat().st_mtime
            except OSError:
                continue
            rows.append((type, slug, gender, entry.suffix.lower(), entry.relative_to(root).as_posix(), mtime))
    with conn:
        conn.execute('DELETE FROM people_images')
        conn.executemany('INSERT OR IGNORE INTO people_images(type, slug, gender, ext, rel_path, mtime) VALUES(?, ?, ?, ?, ?, ?)', rows)
    logger.info('people-cache', f'Rebuilt Local Actor Image Index ({len(rows)} files)')


def _index_file(relpath: str) -> None:
    """Upsert one served file's people_images row from its on-disk state."""
    target = safe_join(people_cache_dir(), relpath)
    if target is None:
        return
    type, slug, gender = parse_person_filename(target.name)
    if not type or not slug:
        return
    try:
        mtime = target.stat().st_mtime
    except OSError:
        return
    conn = _index_conn()
    with conn:
        conn.execute(
            'INSERT OR REPLACE INTO people_images(type, slug, gender, ext, rel_path, mtime) VALUES(?, ?, ?, ?, ?, ?)',
            (type, slug, gender, target.suffix.lower(), relpath, mtime),
        )


def _drop_index_row(relpath: str) -> None:
    conn = _index_conn()
    with conn:
        conn.execute('DELETE FROM people_images WHERE rel_path = ?', (relpath,))


def _scan_miss(conn: sqlite3.Connection, type: PersonType, slug: str) -> tuple[str, str] | None:
    """Manually-dropped files have no row yet: scan the type's subfolders for the
    person and self-heal the index on a hit."""
    root = Path(people_cache_dir())
    subdirs = [f'actors/{bucket}' for bucket in ('male', 'female', 'trans', 'unknown')] if type == 'actor' else [f'{type}s']
    for subdir in subdirs:
        folder = root / subdir
        if not folder.is_dir():
            continue
        for entry in sorted(folder.iterdir()):
            if not entry.is_file() or entry.name.startswith('.') or entry.suffix.lower() not in IMAGE_EXTS:
                continue
            ftype, fslug, gender = parse_person_filename(entry.name)
            if (ftype, fslug) != (type, slug):
                continue
            relpath = f'{subdir}/{entry.name}'
            try:
                mtime = entry.stat().st_mtime
            except OSError:
                continue
            with conn:
                conn.execute(
                    'INSERT OR REPLACE INTO people_images(type, slug, gender, ext, rel_path, mtime) VALUES(?, ?, ?, ?, ?, ?)',
                    (ftype, fslug, gender, entry.suffix.lower(), relpath, mtime),
                )
            return relpath, gender
    return None


def _find_row(type: PersonType, slug: str) -> tuple[str, str] | None:
    """(rel_path, gender) for a cached person: keyed lookup, stale rows healed
    against disk, scan-on-miss fallback for manually-dropped files."""
    conn = _index_conn()
    while True:
        row = conn.execute('SELECT rel_path, gender FROM people_images WHERE type = ? AND slug = ? ORDER BY rel_path LIMIT 1', (type, slug)).fetchone()
        if row is None:
            return _scan_miss(conn, type, slug)
        relpath = str(row['rel_path'])
        target = safe_join(people_cache_dir(), relpath)
        if target is not None and target.is_file():
            return relpath, str(row['gender'])
        with conn:
            conn.execute('DELETE FROM people_images WHERE rel_path = ?', (relpath,))


# ── Public ─────────────────────────────────────────────────────────────────────


def lookup_cached(name: str, type: PersonType) -> dict[str, str] | None:
    if not cache_enabled():
        return None
    found = _find_row(type, _slug(name))
    if found is None:
        return None
    relpath, gender = found
    return {'served_url': _local_url(relpath), 'gender': gender}


async def _download_image(url: str, headers: dict[str, str] | None) -> tuple[bytes, str] | None:
    """Image bytes for the cache. Plain client first; fall back to curl_cffi
    impersonation for Cloudflare-gated hosts (e.g. IAFD headshots 403 a plain GET)."""
    try:
        async with make_http() as client:
            resp = await client.get(url, headers={'User-Agent': 'Mozilla/5.0', **(headers or {})})
            resp.raise_for_status()
            content_type = resp.headers.get('content-type', 'image/jpeg')
            if is_image_content_type(content_type):
                return resp.content, content_type
            logger.debug('people-cache', f'plain fetch returned non-image ({content_type}) for {url}; trying impersonate')
    except (httpx2.HTTPError, OSError) as err:
        logger.debug('people-cache', f'plain fetch failed {url}: {err}; trying impersonate')
    got = await impersonate_get_bytes(url, headers)
    if got:
        logger.debug('people-cache', f'impersonate fetched {url}')
        return got
    logger.warn('people-cache', f'fetch failed {url} (plain + impersonate)')
    return None


async def cache_photo(
    upstream_url: str, name: str, type: PersonType, gender: Gender, headers: dict[str, str] | None = None, source: str = ''
) -> dict[str, str] | None:
    if not cache_enabled():
        return None
    directory = people_cache_dir()
    os.makedirs(directory, exist_ok=True)

    if not cache_replace_enabled():
        existing = lookup_cached(name, type)
        if existing:
            return existing

    fetched = await _download_image(upstream_url, headers)
    if not fetched:
        return None
    data, content_type = fetched

    if len(data) > 20 * 1024 * 1024:
        logger.warn('people-cache', f'image too large {upstream_url}')
        return None

    ext = ext_from(content_type, upstream_url, default='')
    if not ext:
        logger.warn('people-cache', f'invalid extension for {upstream_url} (content-type={content_type})')
        return None

    orig_ext = ext
    original = data
    face_on = env.people_cache_face_enabled and not _is_generic(upstream_url) and source not in _NO_CROP_SOURCES
    cropped = False
    if face_on:
        out = await asyncio.to_thread(face_crop.crop_to_headshot, data)
        if out is not None:
            data, ext, cropped = out, '.jpg', True

    base = _base_name(name, type)
    name_base = f'{base}_{gender}' if gender else base
    filename = f'{name_base}{ext}'
    subdir = _subdir(type, gender)
    relpath = f'{subdir}/{filename}'
    filepath = safe_join(directory, subdir, filename)
    if filepath is None:
        logger.warn('people-cache', f'refusing to write outside cache dir: {relpath}')
        return None
    orig_path = safe_join(directory, _ORIGINALS_DIR, f'{name_base}{orig_ext}') if cropped else None

    def _write() -> None:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_bytes(data)
        if orig_path is not None:
            orig_path.parent.mkdir(parents=True, exist_ok=True)
            orig_path.write_bytes(original)
        face_crop_log.record(str(filepath.parent), name=name, filename=filename, base=name_base, orig_ext=orig_ext, upstream_url=upstream_url, cropped=cropped)

    await asyncio.to_thread(_write)
    _index_file(relpath)
    logger.info('people-cache', f'cached {relpath}{" (face-cropped)" if cropped else ""}')
    return {'served_url': _local_url(relpath, data), 'gender': gender}


_NO_CROP_SOURCES = {'IAFD'}


def _is_generic(url: str) -> bool:
    """True for the silhouette placeholder, which is cached but must never be face-cropped."""
    return bool(url) and url in {generic_image_url('female'), generic_image_url('male')}


def _log_entry(subdir_path: str, filename: str) -> dict[str, Any] | None:
    return face_crop_log.entry_for(subdir_path, filename)


async def restore_original(filename: str) -> bool:
    """Replace a cropped cache file with its un-cropped original: preserved local copy first
    (offline-safe), else re-download upstream. Backs the /people 'Use original' action."""
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
        _drop_index_row(f'{subdir}/{filename}')
    _index_file(f'{subdir}/{target_name}')
    face_crop_log.update(str(subdir_path), filename, filename=target_name, cropped=False)
    logger.info('people-cache', f'restored original for {subdir}/{target_name}')
    return True


def purge(filename: str) -> bool:
    """Delete a cached image (and its preserved original) and drop its crop-log entry.
    Backs the /people 'Purge' button."""
    directory = people_cache_dir()
    subdir = _subdir_for(filename)
    target = safe_join(directory, subdir, filename)
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
    _drop_index_row(f'{subdir}/{filename}')
    face_crop_log.remove(str(target.parent), filename)
    logger.info('people-cache', f'purged {subdir}/{filename}')
    return True


_GENDERS = ('', 'male', 'female', 'trans')


def set_gender(filename: str, new_gender: str) -> str | None:
    """Correct a cached actor's gender: rename the `_<gender>` suffix and MOVE the file (plus
    original and crop-log entry) to actors/<gender>; directors/producers stay put. Returns the new filename."""
    if new_gender not in _GENDERS:
        return None
    directory = people_cache_dir()
    type, slug, old_gender = parse_person_filename(filename)
    root = f'{type}.{slug}' if type else slug
    if not root:
        return None
    ext = Path(filename).suffix
    new_base = f'{root}_{new_gender}' if new_gender else root
    new_filename = f'{new_base}{ext}'
    old_subdir, new_subdir = _subdir(type, old_gender), _subdir(type, new_gender)  # type: ignore[arg-type]

    src = safe_join(directory, old_subdir, filename)
    dst = safe_join(directory, new_subdir, new_filename)
    if src is None or dst is None:
        return None
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
    _drop_index_row(f'{old_subdir}/{filename}')
    _index_file(f'{new_subdir}/{new_filename}')
    logger.info('people-cache', f'gender set to "{new_gender or "none"}" -> {new_subdir}/{new_filename}')
    return new_filename
