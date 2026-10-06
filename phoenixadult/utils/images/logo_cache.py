from __future__ import annotations

import json
import re
import shutil
import sqlite3
import subprocess
import threading
from pathlib import Path
from typing import Any
from urllib.parse import quote

from lxml import etree
from PIL import Image
from PIL.Image import Resampling

from phoenixadult.config.env import env
from phoenixadult.i18n import gettext
from phoenixadult.utils import db
from phoenixadult.utils.fs.paths import rel_to, safe_join
from phoenixadult.utils.images.logo_trim import trim
from phoenixadult.utils.images.proxy import LOCAL_IMAGES
from phoenixadult.utils.logging.logger import logger

_RASTER_EXTS = ('.png', '.jpg', '.jpeg', '.webp')


def cache_dir() -> Path:
    return Path(env.logo_cache_dir)


def logo_slug(name: str) -> str:
    return re.sub(r'[^a-z0-9]', '', name.lower())


def _find_bin(name: str) -> str | None:
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


def _deny_fetch(url: str, *_a: object, **_kw: object) -> bytes:
    raise ValueError(f'external reference refused: {url}')


def _cairosvg(svg: Path, png: Path) -> bool | None:
    try:
        import cairosvg
    except ImportError:
        return None
    try:
        cairosvg.svg2png(url=str(svg), write_to=str(png), url_fetcher=_deny_fetch)
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


_SAFE_HREF_PREFIXES = ('#', 'data:')


def _sanitize_svg(svg: Path) -> bool:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False)
    try:
        tree = etree.parse(str(svg), parser)
    except etree.XMLSyntaxError as err:
        logger.warn('logo-cache', f'{svg.name} is not parseable as SVG: {err}')
        return False
    stripped = 0
    doomed = []
    for el in tree.getroot().iter():
        if not isinstance(el.tag, str):
            continue
        if etree.QName(el).localname.lower() in ('script', 'foreignobject'):
            doomed.append(el)
            continue
        for name in list(el.attrib):
            local = etree.QName(name).localname.lower() if '}' in name else name.lower()
            value = (el.attrib[name] or '').strip()
            if local.startswith('on') or (local == 'href' and not value.lower().startswith(_SAFE_HREF_PREFIXES)):
                del el.attrib[name]
                stripped += 1
    for el in doomed:
        parent = el.getparent()
        if parent is not None:
            parent.remove(el)
            stripped += 1
    if stripped:
        logger.warn('logo-cache', f'stripped {stripped} external or scripted reference(s) from {svg.name}')
    tree.write(str(svg), xml_declaration=True, encoding='utf-8')
    return True


def convert_svg(svg: Path) -> Path | None:
    png = svg.with_suffix('.png')
    if not _sanitize_svg(svg):
        svg.unlink(missing_ok=True)
        return None
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
    _index.reconcile()


def _conn() -> sqlite3.Connection:
    return _index.connect()


def _row_for(f: Path, root: Path) -> tuple[str, str, str, float] | None:
    name_slug = logo_slug(f.name[len('logo.') : -len(f.suffix)])
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


def _folder_dir(folder_slug: str) -> Path | None:
    root = cache_dir()
    if not folder_slug or not root.is_dir():
        return None
    direct = root / folder_slug
    if direct.is_dir():
        return direct
    return next((d for d in sorted(root.iterdir()) if d.is_dir() and logo_slug(d.name) == folder_slug), None)


def _scan_folder(conn: sqlite3.Connection, folder_slug: str) -> None:
    root = cache_dir()
    folder = _folder_dir(folder_slug)
    if folder is None:
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


def _url_for_rel(rel: str, mtime: float | None = None) -> str:
    quoted = '/'.join(quote(part) for part in rel.split('/'))
    bust = f'?v={int(mtime)}' if mtime else ''
    return f'{LOCAL_IMAGES}logos/{quoted}{bust}'


def local_url(path: Path, mtime: float | None = None) -> str | None:
    rel = rel_to(path, cache_dir())
    return None if rel is None else _url_for_rel(rel, mtime)


_WELL_CACHE: dict[str, str] = {}
_WELL_LOADED = False
_WELL_DIRTY = False
_WELL_LOCK = threading.RLock()


def _well_store() -> Path:
    return Path(env.state_db_path).parent / 'logo-wells.json'


def _well_key(rel: str, mtime: float, size: int) -> str:
    return f'{rel}|{int(mtime)}|{size}'


def _load_wells() -> None:
    global _WELL_LOADED
    with _WELL_LOCK:
        _load_wells_locked()


def _load_wells_locked() -> None:
    global _WELL_LOADED
    if _WELL_LOADED:
        return
    _WELL_LOADED = True
    try:
        stored = json.loads(_well_store().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return
    if isinstance(stored, dict):
        _WELL_CACHE.update({str(k): str(v) for k, v in stored.items() if v in ('dark', 'light')})


def _save_wells() -> None:
    with _WELL_LOCK:
        _save_wells_locked()


def _save_wells_locked() -> None:
    global _WELL_DIRTY
    if not _WELL_DIRTY:
        return
    target = _well_store()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(_WELL_CACHE, separators=(',', ':')), encoding='utf-8')
        tmp.replace(target)
    except OSError as err:
        logger.warn('logo-cache', f'could not persist the backdrop cache: {err}')
        return
    _WELL_DIRTY = False


LIGHT_WELL_RGB = (0xF0, 0xF0, 0xF2)
DARK_WELL_RGB = (0x20, 0x20, 0x24)
_INVISIBLE_CONTRAST = 1.5


def _channel(value: int) -> float:
    c = value / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


_CHANNEL = [_channel(v) for v in range(256)]


def _luminance(r: int, g: int, b: int) -> float:
    return 0.2126 * _CHANNEL[r] + 0.7152 * _CHANNEL[g] + 0.0722 * _CHANNEL[b]


def _contrast(a: float, b: float) -> float:
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def preferred_well(path: Path, mtime: float, size: int, rel: str = '') -> str:
    global _WELL_DIRTY

    _load_wells()
    key = _well_key(rel or path.as_posix(), mtime, size)
    with _WELL_LOCK:
        cached = _WELL_CACHE.get(key)
    if cached is not None:
        return cached
    well = 'dark'
    try:
        with Image.open(path) as im:
            converted: Image.Image = im.convert('RGBA')
            converted.thumbnail((96, 96), Resampling.NEAREST)
            raw = converted.tobytes()

        data = [(raw[i], raw[i + 1], raw[i + 2], raw[i + 3]) for i in range(0, len(raw), 4)]
        ink = [(r, g, b) for r, g, b, a in data if a > 128] or [(r, g, b) for r, g, b, a in data if a > 0]
        if ink:
            light_well, dark_well = _luminance(*LIGHT_WELL_RGB), _luminance(*DARK_WELL_RGB)
            lums = [_luminance(*pixel) for pixel in ink]
            lost_on_light = sum(1 for v in lums if _contrast(v, light_well) < _INVISIBLE_CONTRAST)
            lost_on_dark = sum(1 for v in lums if _contrast(v, dark_well) < _INVISIBLE_CONTRAST)
            well = 'dark' if lost_on_dark <= lost_on_light else 'light'
    except Exception as err:  # noqa: BLE001 - an unreadable logo falls back to the dark well
        logger.debug(f'logo-cache: could not read the ink of {path.name}, defaulting to the dark well: {err!r}')
        well = 'dark'
    with _WELL_LOCK:
        _WELL_CACHE[key] = well
        _WELL_DIRTY = True
    return well


def folders() -> list[str]:
    root = cache_dir()
    if not root.exists():
        return []
    return sorted(d.name for d in root.iterdir() if d.is_dir())


def save_logo(folder_slug: str, name_slug: str, data: bytes, suffix: str) -> str:
    if not name_slug:
        raise ValueError(gettext('logo_add.needs_name'))
    suffix = suffix.lower()
    if suffix not in (*_RASTER_EXTS, '.svg'):
        raise ValueError(gettext('logo_add.unsupported_type') % {'suffix': suffix})
    root = cache_dir()
    target_dir = (_folder_dir(folder_slug) or root / folder_slug) if folder_slug else root
    target_dir.mkdir(parents=True, exist_ok=True)
    for existing in target_dir.glob(f'logo.{name_slug}.*'):
        existing.unlink(missing_ok=True)
    target = target_dir / f'logo.{name_slug}{suffix}'
    target.write_bytes(data)
    if suffix == '.svg':
        converted = convert_svg(target)
        if converted is None:
            target.unlink(missing_ok=True)
            raise ValueError(gettext('logo_add.svg_failed'))
        target = converted
    trim(target)
    invalidate()
    reconcile()
    return rel_to(target, root) or target.name


def _prune_wells(live: set[str]) -> None:
    global _WELL_DIRTY

    with _WELL_LOCK:
        stale = set(_WELL_CACHE) - live
        if not stale:
            return
        for key in stale:
            _WELL_CACHE.pop(key, None)
        _WELL_DIRTY = True


def entries() -> list[dict[str, Any]]:
    conn = _conn()
    rows = conn.execute('SELECT name_slug, MIN(rel_path) AS rel_path FROM logos GROUP BY name_slug ORDER BY name_slug').fetchall()
    root = cache_dir()
    out: list[dict[str, Any]] = []
    live_keys: set[str] = set()
    for row in rows:
        rel = str(row['rel_path'])
        path = root / rel
        try:
            stat = path.stat()
        except OSError:
            continue
        live_keys.add(_well_key(rel, stat.st_mtime, stat.st_size))
        out.append(
            {
                'slug': str(row['name_slug']),
                'rel': rel,
                'url': _url_for_rel(rel, stat.st_mtime),
                'sizeBytes': stat.st_size,
                'well': preferred_well(path, stat.st_mtime, stat.st_size, rel),
                'folder': rel.split('/')[0] if '/' in rel else '',
            }
        )
    _prune_wells(live_keys)
    _save_wells()
    return out


def purge(rel: str) -> bool:
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


def _trim_stored() -> int:
    root = cache_dir()
    if not root.exists():
        return 0
    trimmed = 0
    for f in sorted(root.rglob('logo.*')):
        if f.is_file() and f.suffix.lower() in _RASTER_EXTS and trim(f) is not None:
            trimmed += 1
    return trimmed


def rescan() -> int:
    _adopt_manual_drops()
    _trim_stored()
    reconcile()
    return len(entries())
