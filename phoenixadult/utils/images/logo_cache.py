from __future__ import annotations

import re
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

from phoenixadult.config import config
from phoenixadult.config.env import env
from phoenixadult.utils import db
from phoenixadult.utils.fs.paths import rel_to
from phoenixadult.utils.images.ext import ext_from
from phoenixadult.utils.images.image_fetcher import fetch_image
from phoenixadult.utils.logging.logger import logger

_RASTER_EXTS = ('.png', '.jpg', '.jpeg', '.webp')


def enabled() -> bool:
    return env.logo_cache_enabled


def cache_dir() -> Path:
    return Path(env.logo_cache_dir)


def logo_slug(name: str) -> str:
    """Filename slug for a site/studio name: lowercase, spaces to hyphens, other special chars
    removed ('Nubiles.net' -> 'nubilesnet', 'Baby Got Boobs' -> 'baby-got-boobs')."""
    cleaned = re.sub(r'[^a-z0-9 ]', '', name.lower())
    return re.sub(r'\s+', '-', cleaned.strip())


def convert_svg(svg: Path) -> Path | None:
    """Rasterize an SVG logo to a sibling PNG — ImageMagick when installed, cairosvg
    otherwise — deleting the SVG on success."""
    png = svg.with_suffix('.png')
    ok = False
    magick = shutil.which('magick')
    if magick:
        try:
            subprocess.run([magick, '-background', 'none', '-density', '150', str(svg), str(png)], check=True, capture_output=True, timeout=60)
            ok = png.exists() and png.stat().st_size > 0
        except (subprocess.SubprocessError, OSError) as err:
            logger.warn('logo-cache', f'magick conversion failed for {svg.name}: {err!r}')
    if not ok:
        try:
            import cairosvg

            cairosvg.svg2png(url=str(svg), write_to=str(png))
            ok = png.exists() and png.stat().st_size > 0
        except ImportError:
            logger.warn('logo-cache', f'no SVG converter for {svg.name}: install ImageMagick or cairosvg')
        except Exception as err:  # noqa: BLE001 - a bad SVG just stays unconverted
            logger.warn('logo-cache', f'cairosvg conversion failed for {svg.name}: {err!r}')
    if not ok:
        png.unlink(missing_ok=True)
        return None
    svg.unlink(missing_ok=True)
    return png


_index = db.ReconciledConn(lambda: str(cache_dir()), lambda: _rebuild(db.connect()))


def invalidate() -> None:
    _index.invalidate()


def reconcile() -> None:
    """Rebuild the logos table from the files on disk (source of truth)."""
    _index.reconcile()


def _conn() -> sqlite3.Connection:
    return _index.connect()


def _row_for(f: Path, root: Path) -> tuple[str, str, str, float] | None:
    name_slug = f.name[len('logo.') : -len(f.suffix)].lower()
    if not name_slug:
        return None
    rel = f.relative_to(root).as_posix()
    try:
        return rel.rpartition('/')[0], name_slug, rel, f.stat().st_mtime
    except OSError:
        return None


def _rebuild(conn: sqlite3.Connection) -> None:
    rows: list[tuple[str, str, str, float]] = []
    root = cache_dir()
    if root.exists():
        for f in sorted(root.rglob('logo.*')):
            if not f.is_file():
                continue
            if f.suffix.lower() == '.svg':
                converted = convert_svg(f)
                if converted is None:
                    continue
                f = converted
            if f.suffix.lower() not in _RASTER_EXTS:
                continue
            row = _row_for(f, root)
            if row:
                rows.append(row)
    with conn:
        conn.execute('DELETE FROM logos')
        conn.executemany('INSERT OR IGNORE INTO logos(studio_slug, name_slug, rel_path, mtime) VALUES(?, ?, ?, ?)', rows)


def _scan_folder(conn: sqlite3.Connection, folder_slug: str) -> None:
    """Bounded scan-on-miss: index any logo files sitting in one candidate studio folder."""
    root = cache_dir()
    folder = root / folder_slug
    if not folder_slug or not folder.is_dir():
        return
    for f in sorted(folder.iterdir()):
        if not f.is_file() or not f.name.startswith('logo.'):
            continue
        if f.suffix.lower() == '.svg':
            converted = convert_svg(f)
            if converted is None:
                continue
            f = converted
        if f.suffix.lower() not in _RASTER_EXTS:
            continue
        row = _row_for(f, root)
        if row:
            with conn:
                conn.execute('INSERT OR IGNORE INTO logos(studio_slug, name_slug, rel_path, mtime) VALUES(?, ?, ?, ?)', row)


def _lookup(conn: sqlite3.Connection, slug: str) -> Path | None:
    """Keyed logos lookup that heals stale rows: rows whose file is gone are deleted
    and the next candidate row tried; None on a miss."""
    root = cache_dir()
    while True:
        row = conn.execute('SELECT rel_path FROM logos WHERE name_slug = ? ORDER BY rel_path LIMIT 1', (slug,)).fetchone()
        if row is None:
            return None
        path = root / str(row['rel_path'])
        if path.is_file():
            return path
        with conn:
            conn.execute('DELETE FROM logos WHERE rel_path = ?', (row['rel_path'],))


def find_logo(tagline: str | None, studio: str | None) -> Path | None:
    """First cache hit for the tagline slug then the studio slug (serving priority), scanning the two
    candidate studio folders once on a miss; None when disabled or neither name matches a file."""
    if not enabled():
        return None
    conn = _conn()
    scanned = False
    for name in (tagline, studio):
        slug = logo_slug(name) if name else ''
        if not slug:
            continue
        found = _lookup(conn, slug)
        if found is None and not scanned:
            scanned = True
            for candidate in (studio, tagline):
                if candidate:
                    _scan_folder(conn, logo_slug(candidate))
            found = _lookup(conn, slug)
        if found is not None:
            return found
    return None


def local_url(path: Path) -> str | None:
    rel = rel_to(path, cache_dir())
    if rel is None:
        return None
    return f'{config.base_url.rstrip("/")}/images/local/logos/{rel}'


async def resolve_logo(tagline: str | None, studio: str | None, upstream: str | None) -> str | None:
    """Local-first: a cached file always wins; with the cache enabled an upstream URL is downloaded
    ONCE (SVG rasterized) then served locally; with it disabled the upstream passes through untouched."""
    hit = find_logo(tagline, studio)
    if hit:
        return local_url(hit) or upstream
    if not upstream or not enabled():
        return upstream
    saved = await _download(upstream, tagline, studio)
    return (local_url(saved) if saved else None) or upstream


async def _download(url: str, tagline: str | None, studio: str | None) -> Path | None:
    slug = logo_slug(tagline or studio or '')
    folder_slug = logo_slug(studio or tagline or '')
    if not slug or not folder_slug:
        return None
    try:
        entry = await fetch_image(url)
    except Exception as err:  # noqa: BLE001 - a failed download just serves upstream
        logger.warn('logo-cache', f'logo download failed {url}: {err!r}')
        return None
    ext = ext_from(entry.content_type, url, allow_svg=True, default='.png')
    if ext not in (*_RASTER_EXTS, '.svg'):
        ext = '.png'
    folder = cache_dir() / folder_slug
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f'logo.{slug}{ext}'
    target.write_bytes(entry.data)
    if ext == '.svg':
        converted = convert_svg(target)
        if converted is None:
            target.unlink(missing_ok=True)
            return None
        target = converted
    rel = target.relative_to(cache_dir()).as_posix()
    conn = _conn()
    with conn:
        conn.execute(
            'INSERT OR REPLACE INTO logos(studio_slug, name_slug, rel_path, mtime) VALUES(?, ?, ?, ?)', (folder_slug, slug, rel, target.stat().st_mtime)
        )
    logger.info('logo-cache', f'logo saved {rel}')
    return target


def entries() -> list[dict[str, Any]]:
    """All cached logos for the review UI, straight from the logos table."""
    conn = _conn()
    rows = conn.execute('SELECT name_slug, MIN(rel_path) AS rel_path FROM logos GROUP BY name_slug ORDER BY name_slug').fetchall()
    root = cache_dir()
    out: list[dict[str, Any]] = []
    for row in rows:
        rel = str(row['rel_path'])
        path = root / rel
        try:
            size = path.stat().st_size
        except OSError:
            continue
        out.append({'slug': str(row['name_slug']), 'rel': rel, 'url': local_url(path), 'sizeBytes': size, 'folder': rel.split('/')[0] if '/' in rel else ''})
    return out


def purge(rel: str) -> bool:
    from phoenixadult.utils.fs.paths import safe_join

    target = safe_join(str(cache_dir()), rel)
    if not target or not target.is_file() or not target.name.startswith('logo.'):
        return False
    rel_key = target.relative_to(cache_dir().resolve()).as_posix()
    target.unlink()
    conn = _conn()
    with conn:
        conn.execute('DELETE FROM logos WHERE rel_path = ?', (rel_key,))
    return True


def purge_all() -> int:
    root = cache_dir()
    count = 0
    if root.exists():
        for f in list(root.rglob('logo.*')):
            if f.is_file():
                f.unlink()
                count += 1
    conn = _conn()
    with conn:
        conn.execute('DELETE FROM logos')
    return count
