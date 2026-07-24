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
from phoenixadult.utils.logging.logger import logger

_RASTER_EXTS = ('.png', '.jpg', '.jpeg', '.webp')


def cache_dir() -> Path:
    return Path(env.logo_cache_dir)


def logo_slug(name: str) -> str:
    """Filename slug for a site/studio name: lowercase, spaces to hyphens, other special chars
    removed ('Nubiles.net' -> 'nubilesnet', 'Baby Got Boobs' -> 'baby-got-boobs')."""
    cleaned = re.sub(r'[^a-z0-9 ]', '', name.lower())
    return re.sub(r'\s+', '-', cleaned.strip())


def _find_bin(name: str) -> str | None:
    """`name` on PATH, else the usual install prefixes — daemon(8) often runs with a PATH
    that omits /usr/local/bin, so shutil.which alone misses an installed binary."""
    found = shutil.which(name)
    if found:
        return found
    for prefix in ('/usr/local/bin', '/usr/bin', '/opt/homebrew/bin'):
        if (candidate := Path(prefix) / name).is_file():
            return str(candidate)
    return None


def _rsvg(svg: Path, png: Path) -> bool:
    rsvg = _find_bin('rsvg-convert')
    if not rsvg:
        return False
    try:
        subprocess.run([rsvg, '-z', '2', '-o', str(png), str(svg)], check=True, capture_output=True, timeout=60)
        return png.exists() and png.stat().st_size > 0
    except (subprocess.SubprocessError, OSError) as err:
        logger.warn('logo-cache', f'rsvg-convert failed for {svg.name}: {err!r}')
        return False


def _cairosvg(svg: Path, png: Path) -> bool | None:
    """None = cairosvg not installed (try the next converter); True/False = attempt outcome."""
    try:
        import cairosvg
    except ImportError:
        return None
    try:
        cairosvg.svg2png(url=str(svg), write_to=str(png))
        return png.exists() and png.stat().st_size > 0
    except Exception as err:  # noqa: BLE001 - a bad SVG just stays unconverted
        logger.warn('logo-cache', f'cairosvg failed for {svg.name}: {err!r}')
        return False


def _magick(svg: Path, png: Path) -> bool:
    magick = _find_bin('magick')
    if not magick:
        return False
    try:
        subprocess.run([magick, '-background', 'none', '-density', '150', str(svg), str(png)], check=True, capture_output=True, timeout=60)
        return png.exists() and png.stat().st_size > 0
    except (subprocess.SubprocessError, OSError) as err:
        logger.warn('logo-cache', f'magick conversion failed for {svg.name}: {err!r}')
        return False


def convert_svg(svg: Path) -> Path | None:
    """Rasterize an SVG logo to a sibling PNG (deletes the SVG on success). Prefers rsvg-convert
    then cairosvg; ImageMagick is last as its built-in renderer mangles masks into white blocks."""
    png = svg.with_suffix('.png')
    ok = _rsvg(svg, png) or _cairosvg(svg, png) or _magick(svg, png)
    if not ok:
        logger.warn('logo-cache', f'no working SVG converter for {svg.name}: install graphics/librsvg2-rust (rsvg-convert) or cairosvg')
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
    """First cache hit for the tagline slug then the studio slug (match priority), scanning the two
    candidate studio folders once on a miss; None when neither name matches a file."""
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


def _adopt_manual_drops() -> int:
    """Rename manually-dropped logo files (any name) to `logo.<slug>.<ext>` so the reconcile
    picks them up; the studio folder is the drop target, the file stem becomes the name slug."""
    root = cache_dir()
    if not root.exists():
        return 0
    adopted = 0
    for f in sorted(root.rglob('*')):
        if not f.is_file() or f.name.startswith('logo.') or f.name.startswith('.'):
            continue
        if f.suffix.lower() not in (*_RASTER_EXTS, '.svg'):
            continue
        slug = logo_slug(f.stem)
        if not slug:
            continue
        target = f.with_name(f'logo.{slug}{f.suffix.lower()}')
        if target.exists():
            continue
        f.rename(target)
        adopted += 1
    return adopted


def rescan() -> int:
    """Adopt manual drops then rebuild the index (converting any SVG to PNG), so a
    hand-placed logo is served without a restart. Returns the number of cached logos."""
    _adopt_manual_drops()
    reconcile()
    return len(entries())
