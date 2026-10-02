from __future__ import annotations

import hashlib
import re
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, get_args
from urllib.parse import quote

import httpx2
from cachetools import LRUCache

from phoenixadult.config import image_base_url
from phoenixadult.config.env import env
from phoenixadult.utils import db
from phoenixadult.utils.auth.url_signing import sign_url
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.fs.paths import safe_join
from phoenixadult.utils.http.client import read_capped, shared_http
from phoenixadult.utils.http.impersonate import impersonate_get_bytes
from phoenixadult.utils.http.ssrf_guard import guard_target
from phoenixadult.utils.images import face_crop, face_crop_log
from phoenixadult.utils.images.ext import IMAGE_EXTS, ext_from, is_image_content_type
from phoenixadult.utils.images.image_fetcher import max_image_bytes
from phoenixadult.utils.images.proxy import LOCAL_IMAGES
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.people.image_source import GENERIC_SOURCE, source_for_url
from phoenixadult.utils.people.types import GENDER_SUFFIXES, Gender, PersonType, parse_person_filename


def _slug(name: str) -> str:
    return re.sub(r'\s+', '-', re.sub(r'\.{2,}', '.', re.sub(r'[/\\]', '-', name))).lower()


ORIGINALS_DIR = 'originals'


def _base_name(name: str, type: PersonType) -> str:
    return f'{type}.{_slug(name)}'


def _subdir(type: PersonType, gender: Gender) -> str:
    if type == 'actor':
        bucket = gender if gender in GENDER_SUFFIXES else 'unknown'
        return f'actors/{bucket}'
    return f'{type}s'


def _subdir_for(filename: str) -> str:
    type, _, gender = parse_person_filename(filename)
    return _subdir(type, gender)  # type: ignore[arg-type]


_bust_cache: LRUCache[str, tuple[float, str]] = LRUCache(maxsize=8192)


def _bust_token(relpath: str, data: bytes | None) -> str:
    if data is not None:
        return hashlib.sha1(data).hexdigest()[:8]  # noqa: S324 - cache-bust, not security
    path = safe_join(env.people_cache_dir, relpath)
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
    token = _bust_token(relpath, data)
    bust = f'?v={token}' if token else ''
    quoted = '/'.join(quote(part) for part in relpath.split('/'))
    return sign_url(f'{image_base_url()}{LOCAL_IMAGES}{quoted}{bust}') or ''


# ── Index (people_images table; files are the source of truth) ────────────────


_index = db.ReconciledConn(lambda: env.people_cache_dir, lambda: _rebuild_index(db.connect()))


def _served_files(root: Path) -> Iterator[Path]:
    for entry in root.rglob('*'):
        if not entry.is_file() or entry.name.startswith('.') or entry.suffix.lower() not in IMAGE_EXTS:
            continue
        if entry.relative_to(root).parts[0] == ORIGINALS_DIR:
            continue
        yield entry


def reconcile() -> None:
    _index.reconcile()


def index_conn() -> sqlite3.Connection:
    return _index.connect()


def _rebuild_index(conn: sqlite3.Connection) -> None:
    root = Path(env.people_cache_dir)
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
    target = safe_join(env.people_cache_dir, relpath)
    if target is None:
        return
    type, slug, gender = parse_person_filename(target.name)
    if not type or not slug:
        return
    try:
        mtime = target.stat().st_mtime
    except OSError:
        return
    conn = index_conn()
    with conn:
        conn.execute(
            'INSERT OR REPLACE INTO people_images(type, slug, gender, ext, rel_path, mtime) VALUES(?, ?, ?, ?, ?, ?)',
            (type, slug, gender, target.suffix.lower(), relpath, mtime),
        )


def _drop_index_row(relpath: str) -> None:
    conn = index_conn()
    with conn:
        conn.execute('DELETE FROM people_images WHERE rel_path = ?', (relpath,))


def _scan_miss(conn: sqlite3.Connection, type: PersonType, slug: str) -> tuple[str, str] | None:
    root = Path(env.people_cache_dir)
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
    conn = index_conn()
    while True:
        row = conn.execute('SELECT rel_path, gender FROM people_images WHERE type = ? AND slug = ? ORDER BY rel_path LIMIT 1', (type, slug)).fetchone()
        if row is None:
            return _scan_miss(conn, type, slug)
        relpath = str(row['rel_path'])
        target = safe_join(env.people_cache_dir, relpath)
        if target is not None and target.is_file():
            return relpath, str(row['gender'])
        with conn:
            conn.execute('DELETE FROM people_images WHERE rel_path = ?', (relpath,))


# ── Public ─────────────────────────────────────────────────────────────────────


def lookup_cached(name: str, type: PersonType) -> dict[str, str] | None:
    if not env.people_cache_enabled:
        return None
    found = _find_row(type, _slug(name))
    if found is None:
        return None
    relpath, gender = found
    return {'served_url': _local_url(relpath), 'gender': gender}


async def _download_image(url: str, headers: dict[str, str] | None) -> tuple[bytes, str] | None:
    try:
        await guard_target(url)
    except ValueError as err:
        logger.warn('people-cache', f'refusing to fetch {url}: {err}')
        return None
    try:
        async with shared_http('people-image').stream('GET', url, headers={'User-Agent': 'Mozilla/5.0', **(headers or {})}) as resp:
            resp.raise_for_status()
            content_type = resp.headers.get('content-type', 'image/jpeg')
            if is_image_content_type(content_type):
                return await read_capped(resp, max_image_bytes()), content_type
        logger.debug('people-cache', f'plain fetch returned non-image ({content_type}) for {url}; trying impersonate')
    except (httpx2.HTTPError, OSError, ValueError) as err:
        logger.debug('people-cache', f'plain fetch failed {url}: {err}; trying impersonate')
    got = await impersonate_get_bytes(url, headers)
    if got:
        logger.debug('people-cache', f'impersonate fetched {url}')
        return got
    logger.warn('people-cache', f'fetch failed {url} (plain + impersonate)')
    return None


@dataclass
class _Headshot:
    data: bytes
    ext: str
    original: bytes
    orig_ext: str
    cropped: bool = False


async def _fetch_headshot(upstream_url: str, headers: dict[str, str] | None) -> _Headshot | None:
    fetched = await _download_image(upstream_url, headers)
    if not fetched:
        return None
    data, content_type = fetched
    if len(data) > max_image_bytes():
        logger.warn('people-cache', f'image too large {upstream_url}')
        return None
    ext = ext_from(content_type, upstream_url, default='')
    if not ext:
        logger.warn('people-cache', f'invalid extension for {upstream_url} (content-type={content_type})')
        return None
    return _Headshot(data, ext, data, ext)


async def _crop(shot: _Headshot) -> None:
    out = await run_in('image', face_crop.crop_to_headshot, shot.data)
    if out is not None:
        shot.data, shot.ext, shot.cropped = out, '.jpg', True


def _write_headshot(filepath: Path, orig_path: Path | None, shot: _Headshot, log: dict[str, Any]) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_bytes(shot.data)
    if orig_path is not None:
        orig_path.parent.mkdir(parents=True, exist_ok=True)
        orig_path.write_bytes(shot.original)
    face_crop_log.record(str(filepath.parent), orig_ext=shot.orig_ext, cropped=shot.cropped, **log)


async def cache_photo(
    upstream_url: str,
    name: str,
    type: PersonType,
    gender: Gender,
    headers: dict[str, str] | None = None,
    source: str = '',
    *,
    replace: bool = False,
    crop: bool | None = None,
) -> dict[str, str] | None:
    if not env.people_cache_enabled:
        return None
    directory = env.people_cache_dir
    source = source or source_for_url(upstream_url)
    reuse = not replace and not env.people_cache_replace_enabled

    def _prepare() -> dict[str, str] | None:
        Path(directory).mkdir(parents=True, exist_ok=True)
        return lookup_cached(name, type) if reuse else None

    existing = await run_in('fs', _prepare)
    if existing:
        return existing
    shot = await _fetch_headshot(upstream_url, headers)
    if shot is None:
        return None
    face_on = crop if crop is not None else (env.people_cache_face_enabled and source not in _NO_CROP_SOURCES)
    if face_on:
        await _crop(shot)

    base = _base_name(name, type)
    name_base = f'{base}_{gender}' if gender else base
    filename = f'{name_base}{shot.ext}'
    subdir = _subdir(type, gender)
    relpath = f'{subdir}/{filename}'
    filepath = safe_join(directory, subdir, filename)
    if filepath is None:
        logger.warn('people-cache', f'refusing to write outside cache dir: {relpath}')
        return None
    orig_path = safe_join(directory, ORIGINALS_DIR, f'{name_base}{shot.orig_ext}') if shot.cropped else None
    log = {'name': name, 'filename': filename, 'base': name_base, 'upstream_url': upstream_url, 'source': source}
    await run_in('fs', _write_headshot, filepath, orig_path, shot, log)
    await run_in('store', _index_file, relpath)
    logger.info('people-cache', f'cached {relpath} from {source or "an unrecorded source"}{" (face-cropped)" if shot.cropped else ""}')
    return {'served_url': _local_url(relpath, shot.data), 'gender': gender}


_NO_CROP_SOURCES = {'IAFD', GENERIC_SOURCE}


async def _original_bytes(directory: str, entry: dict[str, Any]) -> bytes | None:
    local = safe_join(directory, ORIGINALS_DIR, f'{entry["base"]}{entry.get("orig_ext") or ".jpg"}')

    def _read_local() -> bytes | None:
        return local.read_bytes() if local is not None and local.exists() else None

    data: bytes | None = await run_in('fs', _read_local)
    if data is None and entry.get('upstream_url'):
        fetched = await _download_image(entry['upstream_url'], None)
        data = fetched[0] if fetched else None
    return data


def _swap_in_original(directory: str, subdir: str, filename: str, target: Path, target_name: str, payload: bytes, log_dir: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    if target_name != filename:
        stale = safe_join(directory, subdir, filename)
        if stale is not None and stale != target and stale.exists():
            stale.unlink()
        _drop_index_row(f'{subdir}/{filename}')
    _index_file(f'{subdir}/{target_name}')
    face_crop_log.update(log_dir, filename, filename=target_name, cropped=False)


async def restore_original(filename: str) -> bool:
    directory = env.people_cache_dir
    subdir = _subdir_for(filename)
    subdir_path = safe_join(directory, subdir)
    entry = face_crop_log.entry_for(str(subdir_path), filename) if subdir_path is not None else None
    if not entry:
        return False
    data = await _original_bytes(directory, entry)
    if data is None:
        logger.warn('people-cache', f'restore failed for {filename} (no local original or upstream)')
        return False
    target_name = f'{entry["base"]}{entry.get("orig_ext") or ".jpg"}'
    target = safe_join(directory, subdir, target_name)
    if target is None:
        return False
    await run_in('fs', _swap_in_original, directory, subdir, filename, target, target_name, data, str(subdir_path))
    logger.info('people-cache', f'restored original for {subdir}/{target_name}')
    return True


def purge(filename: str) -> bool:
    directory = env.people_cache_dir
    subdir = _subdir_for(filename)
    target = safe_join(directory, subdir, filename)
    if target is None or not target.exists():
        return False
    try:
        target.unlink()
    except OSError as err:
        logger.warn('people-cache', f'purge failed {filename}: {err}')
        return False
    entry = face_crop_log.entry_for(str(target.parent), filename)
    if entry:
        orig = safe_join(directory, ORIGINALS_DIR, f'{entry["base"]}{entry.get("orig_ext") or ".jpg"}')
        if orig is not None and orig.exists():
            orig.unlink()
    _drop_index_row(f'{subdir}/{filename}')
    face_crop_log.remove(str(target.parent), filename)
    logger.info('people-cache', f'purged {subdir}/{filename}')
    return True


def _replace_file(src: Path, dst: Path) -> bool:
    if dst == src:
        return True
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    src.rename(dst)
    return True


def _rename_original(directory: str, entry: dict[str, Any], new_base: str) -> None:
    orig_ext = entry.get('orig_ext') or '.jpg'
    old_orig = safe_join(directory, ORIGINALS_DIR, f'{entry["base"]}{orig_ext}')
    new_orig = safe_join(directory, ORIGINALS_DIR, f'{new_base}{orig_ext}')
    if old_orig is None or new_orig is None or old_orig == new_orig or not old_orig.exists():
        return
    if new_orig.exists():
        new_orig.unlink()
    old_orig.rename(new_orig)


def _relog(entry: dict[str, Any] | None, old_log: str, new_log: str, filename: str, new_filename: str, new_base: str, *, moved: bool) -> None:
    if not moved:
        face_crop_log.update(old_log, filename, filename=new_filename, base=new_base)
        return
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
            source=entry.get('source', ''),
        )


def set_gender(filename: str, new_gender: str) -> str | None:
    if new_gender not in get_args(Gender):
        return None
    directory = env.people_cache_dir
    type, slug, old_gender = parse_person_filename(filename)
    root = f'{type}.{slug}' if type else slug
    if not root:
        return None
    new_base = f'{root}_{new_gender}' if new_gender else root
    new_filename = f'{new_base}{Path(filename).suffix}'
    old_subdir, new_subdir = _subdir(type, old_gender), _subdir(type, new_gender)  # type: ignore[arg-type]
    src = safe_join(directory, old_subdir, filename)
    dst = safe_join(directory, new_subdir, new_filename)
    if src is None or dst is None or not _replace_file(src, dst):
        return None
    entry = face_crop_log.entry_for(str(src.parent), filename)
    if entry:
        _rename_original(directory, entry, new_base)
    _relog(entry, str(src.parent), str(dst.parent), filename, new_filename, new_base, moved=old_subdir != new_subdir)
    _drop_index_row(f'{old_subdir}/{filename}')
    _index_file(f'{new_subdir}/{new_filename}')
    logger.info('people-cache', f'gender set to "{new_gender or "none"}" -> {new_subdir}/{new_filename}')
    return new_filename
