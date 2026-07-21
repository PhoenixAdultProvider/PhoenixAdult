from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app.config import config
from app.config.env import env
from app.utils.images.image_fetcher import fetch_image
from app.utils.logging.logger import logger

_RASTER_EXTS = ('.png', '.jpg', '.jpeg', '.webp')
_CT_EXTS = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp', 'image/svg+xml': '.svg'}
_SCAN_INTERVAL = 30.0

_index: dict[str, Path] = {}
_scanned_at = 0.0
_scanned_dir = ''


def enabled() -> bool:
    return env.logo_cache_enabled


def cache_dir() -> Path:
    return Path(env.logo_cache_dir)


def logo_slug(name: str) -> str:
    """The filename slug for a site/studio name: lowercase, spaces to hyphens, every
    other special char removed ('Nubiles.net' -> 'nubilesnet', 'Baby Got Boobs' ->
    'baby-got-boobs')."""
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


def _rebuild() -> None:
    global _index
    idx: dict[str, Path] = {}
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
            slug = f.name[len('logo.') : -len(f.suffix)].lower()
            if slug:
                idx.setdefault(slug, f)
    _index = idx


def invalidate() -> None:
    global _scanned_at
    _scanned_at = 0.0


def _ensure_index() -> None:
    global _scanned_at, _scanned_dir
    now = time.monotonic()
    if _scanned_at and now - _scanned_at < _SCAN_INTERVAL and _scanned_dir == str(cache_dir()):
        return
    _scanned_at = now
    _scanned_dir = str(cache_dir())
    _rebuild()


def find_logo(tagline: str | None, studio: str | None) -> Path | None:
    """First cache hit for the tagline then the studio (serving priority), None when
    the logo cache is disabled or neither name matches a file."""
    if not enabled():
        return None
    _ensure_index()
    for name in (tagline, studio):
        if name and (hit := _index.get(logo_slug(name))):
            return hit
    return None


def local_url(path: Path) -> str | None:
    try:
        rel = path.resolve().relative_to(cache_dir().resolve())
    except (ValueError, OSError):
        return None
    return f'{config.base_url.rstrip("/")}/images/local/logos/{rel.as_posix()}'


async def resolve_logo(tagline: str | None, studio: str | None, upstream: str | None) -> str | None:
    """Local-first resolution: a cached file always wins; with the cache enabled an
    upstream URL is downloaded ONCE (SVG rasterized) and served locally from then on;
    with it disabled the upstream URL passes through untouched (or None)."""
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
    ext = _CT_EXTS.get(entry.content_type.split(';')[0].strip().lower()) or Path(urlsplit(url).path).suffix.lower()
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
    logger.info('logo-cache', f'logo saved {target.relative_to(cache_dir())}')
    invalidate()
    return target


def entries() -> list[dict[str, Any]]:
    """All cached logos for the review UI, freshly rescanned."""
    invalidate()
    _ensure_index()
    out = []
    for slug, path in sorted(_index.items()):
        rel = path.relative_to(cache_dir()).as_posix()
        out.append({'slug': slug, 'rel': rel, 'url': local_url(path), 'sizeBytes': path.stat().st_size, 'folder': rel.split('/')[0] if '/' in rel else ''})
    return out


def purge(rel: str) -> bool:
    from app.utils.fs.paths import safe_join

    target = safe_join(str(cache_dir()), rel)
    if not target or not target.is_file() or not target.name.startswith('logo.'):
        return False
    target.unlink()
    invalidate()
    return True


def purge_all() -> int:
    root = cache_dir()
    count = 0
    if root.exists():
        for f in list(root.rglob('logo.*')):
            if f.is_file():
                f.unlink()
                count += 1
    invalidate()
    return count
