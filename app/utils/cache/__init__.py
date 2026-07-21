from __future__ import annotations

import asyncio
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
from app.models.metadata import PlexCollection, PlexGenre, PlexImage, PlexMetadataResponse, PlexRole
from app.registry import SITE_DEFINITIONS, find_site
from app.utils.fs.paths import safe_join
from app.utils.genres import NormalizeGenresOptions, normalize_genres
from app.utils.helpers.helpers import slugify
from app.utils.images.ext import IMAGE_EXTS
from app.utils.images.image_fetcher import fetch_image
from app.utils.images.proxy import proxy_params
from app.utils.logging.logger import logger
from app.utils.people import PeopleManager, apply_name_aliases, to_plex_roles
from app.utils.processors.studio_name import normalize_studio
from app.utils.processors.text_normalize import normalize_text
from app.utils.processors.title_case import title_case, title_sort

if TYPE_CHECKING:
    from app.clients.base import SceneDetail

_ERROR_TITLE_RE = re.compile(r'\b(404|403|401|500|not found|forbidden|access denied|just a moment|attention required|page not found|error)\b', re.IGNORECASE)

_index: dict[str, str] | None = None
_index_dir: str | None = None
_write_locks: dict[str, asyncio.Lock] = {}
_write_lock_users: dict[str, int] = {}


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
    """Stable leaf-dir name for a scene, derivable from the ratingKey alone (cache-first reads),
    scoped by the resolved site so two sites sharing a cur_id don't collide."""
    site = find_site(site_name)
    base = site.name if site else site_name
    raw = f'{slugify(base)}\n{cur_id}'
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]  # noqa: S324 - non-crypto key


def _rel_dir(site_name: str, studio: str, tagline: str) -> str:
    """On-disk folder per the site's `cache_layout`: 'network' → <scraper>/<studio>, 'aggregator' →
    <scraper>/<studio>/<sub-site>, 'studio' → flat, 'auto' → <studio>/<sub-site> for multi-site scrapers."""
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
        for meta_file in root.rglob('meta.json'):
            parent = meta_file.parent
            if parent.name.endswith('.tmp'):
                continue
            idx[parent.name] = parent.relative_to(root).as_posix()
    _index, _index_dir = idx, directory
    logger.info('meta-cache', f'Indexed {len(idx)} snapshot(s) ({directory})')
    return _index


# ── Data18 Manual-Mapping Change Detection ────────────────────────────────────


def _data18_fingerprint(response: PlexMetadataResponse) -> str:
    """The data18 manual-mapping URL this scene resolves to (empty if unmapped),
    recomputed from the snapshot so a mapping edit can be detected on serve."""
    from app.clients.aggregators.data18 import manual_mapping_url, mapping_slug

    try:
        md = response.MediaContainer.Metadata[0]
    except (AttributeError, IndexError):
        return ''
    return manual_mapping_url(mapping_slug(md.title or '', md.tagline or md.studio)) or ''


def _stored_data18(response: PlexMetadataResponse) -> dict[str, str] | None:
    try:
        d = response.MediaContainer.Metadata[0].data18
    except (AttributeError, IndexError):
        return None
    return {'type': d.type, 'id': d.id} if d else None


def data18_remap_needed(response: PlexMetadataResponse, site_name: str) -> bool:
    """True if a data18 manual mapping now exists for this cached scene and disagrees with the stored
    ref — so the caller re-scrapes to pick up the override; scenes with no manual mapping are left alone."""
    from app.clients.aggregators.data18 import data18_ref

    if not env.data18_enabled:
        return False
    site = find_site(site_name)
    if not site or not site.scraper_config.data18_enrichment:
        return False
    manual = data18_ref(_data18_fingerprint(response))
    return manual is not None and manual != _stored_data18(response)


def data18_backfill_needed(response: PlexMetadataResponse, site_name: str) -> bool:
    """True if this snapshot is on a data18-enrichment-eligible site but has no data18 ref recorded
    — so a refresh should attempt a fresh scrape to pull enrichment the snapshot predates."""
    if not env.data18_enabled:
        return False
    site = find_site(site_name)
    if not site or not site.scraper_config.data18_enrichment:
        return False
    return any(md.data18 is None and md.title for md in response.MediaContainer.Metadata)


async def backfill_data18(response: PlexMetadataResponse, site_name: str) -> bool:
    """Record a cached scene's data18 ref if its snapshot predates data18 recording; best-effort
    (never breaks a serve), runs only when no ref is stored yet. Returns True if anything changed."""
    from datetime import datetime

    from app.clients.aggregators.data18 import Data18Client, data18_ref, mapping_slug
    from app.models.metadata import PlexData18

    if not env.data18_enabled:
        return False
    site = find_site(site_name)
    if not site or not site.scraper_config.data18_enrichment:
        return False
    pending = [md for md in response.MediaContainer.Metadata if md.data18 is None and md.title]
    if not pending:
        return False

    client = Data18Client()
    changed = False
    for md in pending:
        try:
            date_obj = datetime.fromisoformat(md.originallyAvailableAt) if md.originallyAvailableAt else None
        except ValueError:
            date_obj = None
        providers = [p for p in (md.studio, md.tagline) if p]
        try:
            url = await client.find_scene_url(mapping_slug(md.title, md.tagline or md.studio), md.title, providers, date_obj)
        except Exception as err:  # noqa: BLE001 — backfill must never break the serve
            logger.warn('meta-cache', f'data18 backfill resolve failed for "{md.title}": {err}')
            continue
        if ref := data18_ref(url):
            md.data18 = PlexData18.model_validate(ref)
            changed = True
    return changed


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


def _rebase(obj: Any, base: str, people_base: str) -> Any:
    """Resolve host-relative cached image URLs against the live bases, recursively; people images
    (/images/local/) follow people_base even when a snapshot stored them absolute."""
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

    lock = _write_locks.setdefault(scene_hash, asyncio.Lock())
    _write_lock_users[scene_hash] = _write_lock_users.get(scene_hash, 0) + 1
    try:
        async with lock:
            return await _write_locked(response, scene_hash, rel_path, final_dir)
    finally:
        _write_lock_users[scene_hash] -= 1
        if _write_lock_users[scene_hash] == 0:
            del _write_lock_users[scene_hash]
            _write_locks.pop(scene_hash, None)


async def _write_locked(response: PlexMetadataResponse, scene_hash: str, rel_path: str, final_dir: Path) -> bool:
    tmp_dir = final_dir.parent / f'{scene_hash}.tmp'

    data = response.model_dump(by_alias=True, exclude_none=True)
    meta: dict[str, Any] = data['MediaContainer']['Metadata'][0]
    base = config.base_url.rstrip('/')
    counter = [0]

    shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        sem = asyncio.Semaphore(6)

        def _relativize(u: str) -> str:
            """Strip our own base_url so stored links survive a base_url/tunnel change."""
            return u[len(base) :] if u.startswith(f'{base}/') else u

        async def localize(url: str | None, hint: str) -> str | None:
            """Download an image into the snapshot; people images stay host-relative so
            PEOPLE_IMAGE_URL is re-applied on every serve, whatever base built them."""
            if not url:
                return url
            if '/images/local/' in url:
                return url[url.index('/images/local/') :]
            target, referers, cookies = proxy_params(url)
            name = f'{hint}-{counter[0]:02d}{_ext_of(target)}'
            counter[0] += 1
            try:
                async with sem:
                    entry = await fetch_image(target, referers or None, cookies or None)
                img_dir = tmp_dir / 'images'
                img_dir.mkdir(exist_ok=True)
                (img_dir / name).write_bytes(entry.data)
                return f'/cache/{rel_path}/images/{name}'
            except (httpx2.HTTPError, ValueError, OSError) as err:
                logger.debug('meta-cache', f'image download failed {target}: {err!r}')
                return _relativize(url)

        async def _assign(obj: dict[str, Any], key: str, hint: str) -> None:
            obj[key] = await localize(obj.get(key), hint)

        jobs = []
        if meta.get('thumb'):
            jobs.append(_assign(meta, 'thumb', 'poster'))
        if meta.get('art'):
            jobs.append(_assign(meta, 'art', 'art'))
        jobs.extend(_assign(img, 'url', 'img') for img in meta.get('Image', []))
        for role_key in ('Role', 'Director', 'Producer', 'Writer'):
            jobs.extend(_assign(role, 'thumb', 'role') for role in meta.get(role_key, []) if role.get('thumb'))
        jobs.extend(_assign(rating, 'image', 'rating') for rating in meta.get('Rating', []) if rating.get('image'))
        await asyncio.gather(*jobs)

        (tmp_dir / 'meta.json').write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        if final_dir.exists():
            shutil.rmtree(final_dir, ignore_errors=True)
        tmp_dir.rename(final_dir)
    except OSError as err:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        logger.warn('meta-cache', f'snapshot write failed {rel_path}: {err}')
        return False

    _ensure_index()[scene_hash] = rel_path
    logger.info('meta-cache', f'snapshot saved {rel_path} ({meta.get("title", "")})')
    return True


# ── Management (UI) ──────────────────────────────────────────────────────────


def entries() -> list[dict[str, Any]]:
    """All snapshots, newest first, for the /metadata UI."""
    from app.clients.aggregators.data18 import mapping_slug

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
        d18 = md.get('data18') or {}
        out.append(
            {
                'key': rel,
                'site_slug': segs[-2] if len(segs) >= 2 else rel,
                'studio_dir': segs[-3] if len(segs) >= 3 else '',
                'hash': segs[-1],
                'title': md.get('title', ''),
                'studio': md.get('studio', ''),
                'tagline': md.get('tagline', ''),
                'collections': [t for t in ((c or {}).get('tag', '') for c in md.get('Collection') or []) if t],
                'date': md.get('originallyAvailableAt', ''),
                'thumb': md.get('thumb', ''),
                'images': len(md.get('Image', [])),
                'mtime': mtime,
                'data18_id': d18.get('id', ''),
                'data18_type': d18.get('type', ''),
                'mapping_slug': mapping_slug(md.get('title', ''), md.get('tagline') or md.get('studio')) or '',
            }
        )
    out.sort(key=lambda e: e['mtime'], reverse=True)
    return out


def change_token() -> str:
    """Cheap fingerprint of the snapshot set (count + newest mtime), stat-only —
    the UI polls this and refetches entries only when it changes."""
    root = Path(cache_dir())
    if not root.exists():
        return '0:0'
    count, newest = 0, 0.0
    for mj in root.rglob('meta.json'):
        if mj.parent.name.endswith('.tmp'):
            continue
        try:
            newest = max(newest, mj.stat().st_mtime)
        except OSError:
            continue
        count += 1
    return f'{count}:{newest}'


def purge(key: str) -> bool:
    """Remove one snapshot by its relative path. Leaf dirs only — an intermediate
    studio dir (no meta.json) is refused so one purge can't wipe a whole studio."""
    target = safe_join(cache_dir(), key)
    if target is None or not target.exists() or not (target / 'meta.json').exists():
        return False
    shutil.rmtree(target, ignore_errors=True)
    if _index is not None:
        leaf = key.rsplit('/', 1)[-1]
        if _index.get(leaf) == key:
            del _index[leaf]
    logger.info('meta-cache', f'purged snapshot {key}')
    return True


def duplicate_entries() -> list[str]:
    """Rel paths of sub-site-less snapshots superseded by a sub-site-bearing twin of the same
    scene; a lone sub-site-less snapshot is never reported (its twin is unprovable)."""
    from app.utils.helpers.helpers import b64url_decode, b64url_encode, split_subsite
    from app.utils.plex.rating_key import parse_rating_key

    index = _ensure_index()
    root = Path(cache_dir())
    stale: set[str] = set()
    for rel in set(index.values()):
        try:
            data = json.loads((root / rel / 'meta.json').read_text(encoding='utf-8'))
            rating_key = ((data.get('MediaContainer') or {}).get('Metadata') or [{}])[0].get('ratingKey') or ''
        except (OSError, ValueError):
            continue
        parsed = parse_rating_key(rating_key)
        if not parsed or not parsed['cur_id'] or not parsed['site_name']:
            continue
        try:
            payload, subsite = split_subsite(b64url_decode(parsed['cur_id']))
        except ValueError:
            continue
        if not subsite:
            continue
        old_rel = index.get(_hash(parsed['site_name'], b64url_encode(payload)))
        if old_rel and old_rel != rel:
            stale.add(old_rel)
    return sorted(stale)


def purge_duplicates() -> int:
    return sum(1 for rel in duplicate_entries() if purge(rel))


# ── People-Image Backfill ─────────────────────────────────────────────────────


def _is_stale_local_thumb(thumb: str) -> bool:
    """True if a cached /images/local/ thumb points at a people-cache file that no longer
    exists — so backfill re-resolves it instead of serving a dead link."""
    marker = '/images/local/'
    if marker not in thumb:
        return False
    relpath = unquote(thumb.rsplit(marker, 1)[1].split('?')[0])
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
    """Retry resolving headshots for cached cast/crew entries with no thumb; with `fetch_detail`
    the scene is re-scraped so each person's scene image is tried before external people sources."""
    try:
        md = response.MediaContainer.Metadata[0]
    except (AttributeError, IndexError):
        return False

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
                r.thumb = None
                stale_cleared = True
            if not r.thumb:
                missing.append(f'{key}:{r.tag}')
    if not missing:
        logger.debug('meta-cache', f'backfill skip "{md.title}": all cast/crew already have thumbs')
        return False
    logger.debug('meta-cache', f'backfill "{md.title}" ({site_name}): {len(missing)} imageless -> {", ".join(missing)}')

    fill_groups = [(entries, key) for entries, _role, key in groups]
    changed = stale_cleared

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
            refs = [detail.art_referer] if detail.art_referer else []
            cks = [detail.art_cookie] if detail.art_cookie else []
            if await _resolve_and_fill(scene, fill_groups, studio=detail.studio or md.studio or '', site_name=site_name, referers=refs, cookies=cks):
                changed = True

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


def backfill_logo(response: PlexMetadataResponse) -> bool:
    """Add a clearLogo Image to snapshots written before a logo existed. Mutates in place
    and returns True if anything changed, so the caller can rewrite the snapshot."""
    from app.utils.images import logo_cache

    if not logo_cache.enabled():
        return False
    changed = False
    for md in response.MediaContainer.Metadata:
        if any(img.type == 'clearLogo' for img in md.Image or []):
            continue
        hit = logo_cache.find_logo(md.tagline, md.studio)
        url = logo_cache.local_url(hit) if hit else None
        if not url:
            continue
        md.Image = [*(md.Image or []), PlexImage(url=url, type='clearLogo')]
        changed = True
    return changed


def backfill_metadata_attrs(response: PlexMetadataResponse) -> bool:
    """Add metadata attributes introduced after a snapshot was written and recompute the guid from
    the ratingKey. Mutates in place and returns True if anything changed, so the caller can rewrite."""
    from app.registry import PROVIDER_DEFINITIONS
    from app.utils.plex.rating_key import to_guid

    changed = False
    for md in response.MediaContainer.Metadata:
        if md.ratingKey:
            guid = to_guid(md.ratingKey, PROVIDER_DEFINITIONS[0].plex_identifier)
            if md.guid != guid:
                md.guid = guid
                changed = True
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


def reapply_text_rules(response: PlexMetadataResponse, scraper_type: str | None = None) -> bool:
    """Re-run the current text rules on a cached response; mutates in place and returns True if
    anything changed. Applies new rules to what's stored — it can't restore values dropped at scrape."""
    changed = False
    for md in response.MediaContainer.Metadata:
        studio = md.studio or ''
        title = md.title
        if scraper_type == 'nubiles':
            from app.clients.networks.nubiles import strip_episode_tag

            title = strip_episode_tag(title)
        cased_title = title_case(title, site_name=studio, scraper_type=scraper_type)
        if cased_title and cased_title != md.title:
            md.title = cased_title
            md.titleSort = title_sort(cased_title)
            changed = True
        if md.summary:
            cleaned_summary = normalize_text(md.summary)
            if cleaned_summary != md.summary:
                md.summary = cleaned_summary
                changed = True
        cased_studio = normalize_studio(studio)
        if cased_studio and cased_studio != md.studio:
            md.studio = cased_studio
            changed = True
        if md.tagline:
            cased_tagline = normalize_studio(md.tagline)
            if cased_tagline != md.tagline:
                md.tagline = cased_tagline
                changed = True
        if md.Collection:
            tags = list(dict.fromkeys(normalize_studio(c.tag) for c in md.Collection if c.tag))
            if tags != [c.tag for c in md.Collection]:
                md.Collection = [PlexCollection(tag=t) for t in tags]
                changed = True
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
                cased_name = re.sub(r'\s+', ' ', title_case(r.tag, type='name', site_name=studio)).strip()
                aliased = apply_name_aliases(cased_name, studio, studio)
                if aliased != r.tag:
                    r.tag = aliased
                    changed = True
                if aliased.lower() in seen:
                    changed = True
                    continue
                seen.add(aliased.lower())
                kept.append(r)
            if len(kept) != len(roles):
                setattr(md, attr, kept)
    return changed
