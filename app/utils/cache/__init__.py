from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urlsplit

import httpx2

from app.config import config, people_image_base
from app.config.env import env
from app.models.metadata import PlexGenre, PlexMetadataResponse, PlexRole
from app.registry import SITE_DEFINITIONS, find_site
from app.utils.fs.paths import safe_join
from app.utils.genres import NormalizeGenresOptions, normalize_genres
from app.utils.helpers.helpers import slugify
from app.utils.http.client import make_http
from app.utils.images.ext import IMAGE_EXTS
from app.utils.images.proxy import proxy_target
from app.utils.logging.logger import logger
from app.utils.people import PeopleManager, apply_name_aliases, to_plex_roles
from app.utils.processors.title_case import title_sort

if TYPE_CHECKING:
    from app.clients.base import SceneDetail

_ERROR_TITLE_RE = re.compile(r'\b(404|403|401|500|not found|forbidden|access denied|just a moment|attention required|page not found|error)\b', re.IGNORECASE)

_index: dict[str, str] | None = None
_index_dir: str | None = None


def enabled() -> bool:
    return env.metadata_cache_enabled


def cache_dir() -> str:
    return env.metadata_cache_dir


_scraper_counts: dict[str, int] | None = None


def _scraper_site_count(scraper_type: str) -> int:
    """How many registered sites a scraper drives (cached)."""
    global _scraper_counts
    if _scraper_counts is None:
        counts: dict[str, int] = {}
        for s in SITE_DEFINITIONS:
            counts[s.scraper_config.type] = counts.get(s.scraper_config.type, 0) + 1
        _scraper_counts = counts
    return _scraper_counts.get(scraper_type, 0)


def _hash(site_name: str, cur_id: str) -> str:
    """Stable leaf-dir name for a scene, derivable from the ratingKey alone (so a
    cache-first read can find it before any scrape). Scoped by the resolved site so
    two sites sharing a cur_id don't collide."""
    site = find_site(site_name)
    base = site.name if site else site_name
    raw = f'{slugify(base)}\n{cur_id}'
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]  # noqa: S324 - non-crypto key


def _rel_dir(site_name: str, studio: str, tagline: str) -> str:
    """On-disk folder for a scene, per the site's registry `cache_layout`:
    'network' → <scraper>/<studio>, 'aggregator' → <scraper>/<studio>/<sub-site>,
    'studio' → flat <studio>, 'auto' → <studio>/<sub-site> for multi-site scrapers
    else flat <studio>."""
    site = find_site(site_name)
    studio_slug = slugify(studio) or slugify(site.name if site else site_name) or 'studio'
    layout = site.cache_layout if site else 'auto'
    scraper = slugify(site.scraper_config.type) if site else ''

    if layout == 'studio':
        return studio_slug
    if layout == 'network':
        return f'{scraper}/{studio_slug}' if scraper else studio_slug
    if layout == 'aggregator':
        sub_slug = slugify(tagline) or studio_slug
        return f'{scraper}/{studio_slug}/{sub_slug}' if scraper else f'{studio_slug}/{sub_slug}'
    # auto
    if site and _scraper_site_count(site.scraper_config.type) >= 2:
        return f'{studio_slug}/{slugify(tagline) or studio_slug}'
    return studio_slug


def _ensure_index() -> dict[str, str]:
    global _index, _index_dir
    directory = cache_dir()
    if _index is not None and _index_dir == directory:
        return _index
    idx: dict[str, str] = {}
    root = Path(directory)
    if root.exists():
        # The leaf dir name is the scene hash; map it to the (variable-depth) path.
        for meta_file in root.rglob('meta.json'):
            parent = meta_file.parent
            if parent.name.endswith('.tmp'):
                continue  # half-written snapshot mid-rename
            idx[parent.name] = parent.relative_to(root).as_posix()
    _index, _index_dir = idx, directory
    logger.info('meta-cache', f'Indexed {len(idx)} snapshot(s) ({directory})')
    return _index


# ── Read ─────────────────────────────────────────────────────────────────────


def read(site_name: str, cur_id: str) -> dict[str, Any] | None:
    """Return the frozen PlexMetadataResponse dict, or None if not snapshotted."""
    if not enabled():
        return None
    scene_hash = _hash(site_name, cur_id)
    rel_path = _ensure_index().get(scene_hash)
    if not rel_path:
        return None
    try:
        loaded = json.loads((Path(cache_dir()) / rel_path / 'meta.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as err:
        logger.warn('meta-cache', f'snapshot read failed {rel_path}: {err}')
        return None
    if not isinstance(loaded, dict):
        return None
    rebased = _rebase(loaded, config.base_url.rstrip('/'), people_image_base().rstrip('/'))
    return rebased if isinstance(rebased, dict) else None


# ── Write ────────────────────────────────────────────────────────────────────


def _ext_of(url: str) -> str:
    suffix = Path(urlsplit(url).path).suffix.lower()
    return suffix if suffix in IMAGE_EXTS else '.jpg'


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f'{parts.scheme}://{parts.netloc}/' if parts.scheme and parts.netloc else ''


def _rebase(obj: Any, base: str, people_base: str) -> Any:
    """Resolve host-relative cached image URLs against the live bases, recursively.
    People images (/images/local/) follow PEOPLE_IMAGE_URL (people_base) and are
    normalized even when a snapshot stored them absolute; other links use base_url."""
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


async def write(site_name: str, cur_id: str, response: PlexMetadataResponse) -> bool:
    """Freeze a scraped scene: download images locally, rewrite URLs, persist JSON.
    Skips error-looking titles. Atomic (temp dir + rename). Best-effort per image."""
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
    rel_path = f'{_rel_dir(site_name, (md0.studio or ""), (md0.tagline or ""))}/{scene_hash}'
    final_dir = safe_join(cache_dir(), rel_path)
    if final_dir is None:
        return False
    tmp_dir = final_dir.parent / f'{scene_hash}.tmp'

    data = response.model_dump(by_alias=True, exclude_none=True)
    meta: dict[str, Any] = data['MediaContainer']['Metadata'][0]
    base = config.base_url.rstrip('/')
    counter = [0]

    shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        async with make_http(timeout=20.0) as client:

            def _relativize(u: str) -> str:
                # Strip our own base_url so stored links survive a base_url/tunnel change.
                return u[len(base) :] if u.startswith(f'{base}/') else u

            async def localize(url: str | None, hint: str) -> str | None:
                if not url:
                    return url
                if '/images/local/' in url:
                    # Always store host-relative so the People-image base (PEOPLE_IMAGE_URL)
                    # is re-applied on every serve, whatever base built it.
                    return url[url.index('/images/local/') :]
                target = proxy_target(url)
                name = f'{hint}-{counter[0]:02d}{_ext_of(target)}'
                counter[0] += 1
                try:
                    resp = await client.get(target, headers={'User-Agent': 'Mozilla/5.0', 'Referer': _origin(target)})
                    resp.raise_for_status()
                    img_dir = tmp_dir / 'images'
                    img_dir.mkdir(exist_ok=True)
                    (img_dir / name).write_bytes(resp.content)
                    return f'/cache/{rel_path}/images/{name}'
                except (httpx2.HTTPError, OSError) as err:
                    logger.debug('meta-cache', f'image download failed {target}: {err}')
                    return _relativize(url)  # best-effort: keep the link, host-relative

            if meta.get('thumb'):
                meta['thumb'] = await localize(meta['thumb'], 'poster')
            if meta.get('art'):
                meta['art'] = await localize(meta['art'], 'art')
            for img in meta.get('Image', []):
                img['url'] = await localize(img.get('url'), 'img')
            for role_key in ('Role', 'Director', 'Producer', 'Writer'):
                for role in meta.get(role_key, []):
                    if role.get('thumb'):
                        role['thumb'] = await localize(role['thumb'], 'role')
            for rating in meta.get('Rating', []):
                if rating.get('image'):
                    rating['image'] = await localize(rating['image'], 'rating')

        (tmp_dir / 'meta.json').write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        if final_dir.exists():
            shutil.rmtree(final_dir, ignore_errors=True)
        tmp_dir.rename(final_dir)
    except OSError as err:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        logger.warn('meta-cache', f'snapshot write failed {rel_path}: {err}')
        return False

    if _index is not None:
        _index[scene_hash] = rel_path
    logger.info('meta-cache', f'snapshot saved {rel_path} ({title})')
    return True


# ── Management (UI) ──────────────────────────────────────────────────────────


def entries() -> list[dict[str, Any]]:
    """All snapshots, newest first, for the /metadata-cache UI."""
    out: list[dict[str, Any]] = []
    root = Path(cache_dir())
    if not root.exists():
        return out
    for mj in root.rglob('meta.json'):
        scene = mj.parent
        if scene.name.endswith('.tmp'):
            continue
        try:
            data = json.loads(mj.read_text(encoding='utf-8'))
            md = (data.get('MediaContainer', {}).get('Metadata') or [{}])[0]
            mtime = mj.stat().st_mtime
        except (OSError, ValueError):
            continue
        rel = scene.relative_to(root).as_posix()
        segs = rel.split('/')
        out.append(
            {
                'key': rel,  # full relative path to the scene dir — the purge handle
                'site_slug': segs[-2] if len(segs) >= 2 else rel,
                'studio_dir': segs[-3] if len(segs) >= 3 else '',
                'hash': segs[-1],
                'title': md.get('title', ''),
                'studio': md.get('studio', ''),
                'tagline': md.get('tagline', ''),
                'date': md.get('originallyAvailableAt', ''),
                'thumb': md.get('thumb', ''),
                'images': len(md.get('Image', [])),
                'mtime': mtime,
            }
        )
    out.sort(key=lambda e: e['mtime'], reverse=True)
    return out


def purge(key: str) -> bool:
    """Remove one snapshot by its relative path ('<studio>/<hash>' or
    '<studio>/<sub-site>/<hash>')."""
    target = safe_join(cache_dir(), key)
    if target is None or not target.exists():
        return False
    shutil.rmtree(target, ignore_errors=True)
    if _index is not None:
        leaf = key.rsplit('/', 1)[-1]
        if _index.get(leaf) == key:
            del _index[leaf]
    logger.info('meta-cache', f'purged snapshot {key}')
    return True


# ── People-image backfill ─────────────────────────────────────────────────────


def _is_stale_local_thumb(thumb: str) -> bool:
    """True if a cached /images/local/ thumb points at a people-cache file that no longer
    exists (e.g. purged at /people-cache) — so backfill re-resolves it instead of serving
    a dead link."""
    marker = '/images/local/'
    if marker not in thumb:
        return False
    relpath = unquote(thumb.rsplit(marker, 1)[1].split('?')[0])  # e.g. actors/female/x.jpg
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
    """Resolve the people enqueued on `people` and copy any newly-found thumb onto a
    still-imageless snapshot role, matched by canonical tag. True if anything changed."""
    try:
        resolved = await people.resolve_all(studio=studio, site_name=site_name, referers=referers, cookies=cookies)
    except Exception as err:  # noqa: BLE001 — backfill must never break the serve
        logger.warn('meta-cache', f'people-image backfill resolve failed: {err}')
        return False
    changed = False
    for entries, key in fill_groups:
        roles = to_plex_roles(resolved[key], people_image_base(), referers or [], cookies or [])
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
    """Retry resolving headshots for cached cast / director / producer entries with no thumb.

    When `fetch_detail` is given, the scene is re-scraped first so each person's *scene*
    image is tried before external people sources (mirroring a fresh scrape); people the
    scene doesn't list still fall back to the sources. Best-effort (never breaks a serve)
    and self-healing — once an image is found the snapshot is re-written, so only still-
    imageless people retry. Shared by the live agent (MetadataService) and the /dev flow.
    """
    try:
        md = response.MediaContainer.Metadata[0]
    except (AttributeError, IndexError):
        return False

    # (snapshot entries, role, resolve_all() output key)
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
                r.thumb = None  # cached file was purged — drop the dead link and re-resolve below
                stale_cleared = True
            if not r.thumb:
                missing.append(f'{key}:{r.tag}')
    if not missing:
        logger.debug('meta-cache', f'backfill skip "{md.title}": all cast/crew already have thumbs')
        return False
    logger.debug('meta-cache', f'backfill "{md.title}" ({site_name}): {len(missing)} imageless -> {", ".join(missing)}')

    fill_groups = [(entries, key) for entries, _role, key in groups]
    changed = stale_cleared  # clearing a purged thumb is itself a change worth persisting

    # Phase 1 — the scene's own images first (mirrors a fresh scrape), when re-fetchable.
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
            refs = [detail.raw_image_referer] if detail.raw_image_referer else []
            cks = [detail.raw_image_cookie] if detail.raw_image_cookie else []
            if await _resolve_and_fill(scene, fill_groups, studio=detail.studio or md.studio or '', site_name=site_name, referers=refs, cookies=cks):
                changed = True

    # Phase 2 — external people sources for anyone still imageless (incl. people the scene omits).
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
    """Add metadata attributes introduced after a snapshot was written (contentRating,
    isAdult, titleSort, Role order). Mutates in place and returns True if anything
    changed, so the caller can rewrite the snapshot."""
    changed = False
    for md in response.MediaContainer.Metadata:
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


def reapply_text_rules(response: PlexMetadataResponse) -> bool:
    """Re-run genre normalization + actor alias tables on a cached response using the
    current genres.json / actors.json (both hot-reload on edit). Mutates in place and
    returns True if anything changed, so the caller can rewrite the snapshot. It applies
    new skip/rename/alias rules to what's stored; it can't restore values dropped at the
    original scrape (those aren't in the snapshot — purge to re-scrape)."""
    changed = False
    for md in response.MediaContainer.Metadata:
        studio = md.studio or ''
        if md.Genre:
            old = [g.tag for g in md.Genre]
            new = normalize_genres(old, NormalizeGenresOptions(title=md.title, site_name=studio))
            if new != old:
                md.Genre = [PlexGenre(tag=t) for t in new]
                changed = True
        for attr in ('Role', 'Director', 'Producer'):
            roles: list[PlexRole] | None = getattr(md, attr)
            if not roles:
                continue
            seen: set[str] = set()
            kept: list[PlexRole] = []
            for r in roles:
                aliased = apply_name_aliases(r.tag, studio, studio)
                if aliased != r.tag:
                    r.tag = aliased
                    changed = True
                if aliased.lower() in seen:  # an alias collapsed two cast members
                    changed = True
                    continue
                seen.add(aliased.lower())
                kept.append(r)
            if len(kept) != len(roles):
                setattr(md, attr, kept)
    return changed
