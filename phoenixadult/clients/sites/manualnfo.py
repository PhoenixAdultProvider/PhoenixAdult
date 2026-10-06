from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from html.entities import html5
from pathlib import Path
from typing import Any
from urllib.parse import quote
from xml.etree import ElementTree as ET

from lxml import etree as lxml_etree

from phoenixadult.clients.base import Client, LoadedScene
from phoenixadult.config import config
from phoenixadult.config.env import env
from phoenixadult.models.scrape import ActorResult, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.auth.url_signing import sign_url
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.helpers.data18 import scene_url_from_ref
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result
from phoenixadult.utils.helpers.text import slugify
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.people.types import GENDER_SUFFIXES
from phoenixadult.utils.processors.filename_parser import clean_search_title

_IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.webp')
_INDEX_TTL_S = 60.0
_MISS_THROTTLE_S = 2.0

_XML_DECL_RE = re.compile(r'^\s*<\?xml[^>]*\?>')
_XML_ENTITY_RE = re.compile(r'&(?:#\d+|#x[0-9a-fA-F]+|amp|lt|gt|quot|apos);')
_AMP_RE = re.compile(r'&(#\d+;|#x[0-9a-fA-F]+;|[A-Za-z][A-Za-z0-9]*;)?')
_TAG_START_RE = re.compile(r'<(?:[A-Za-z_/?!])')
_BAD_CHAR_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')


@dataclass
class LocatedNfo:
    layout: str
    basename: str
    nfo_path: Path
    sibling_dir: Path


@dataclass
class NfoData:
    title: str
    genres: list[str] = field(default_factory=list)
    actors: list[dict[str, str]] = field(default_factory=list)
    set: str | None = None
    year: str | None = None
    outline: str | None = None
    plot: str | None = None
    tagline: str | None = None
    release_date: str | None = None
    studio: str | None = None
    thumb: str | None = None
    fanart: str | None = None
    data18: str | None = None


@dataclass
class _CachedIndex:
    by_basename: dict[str, LocatedNfo]
    by_normalized: dict[str, LocatedNfo]
    root: str
    built_at: float


def _normalize_basename(basename: str) -> str:
    return clean_search_title(basename).strip(' ._-').casefold()


_cached_index: _CachedIndex | None = None
_index_lock = threading.Lock()


def _manual_nfo_root() -> str:
    return env.manual_nfo_path


def _build_index(root: str) -> _CachedIndex:
    winners: dict[str, tuple[LocatedNfo, int]] = {}
    root_path = Path(root)
    nfo_files: list[Path] = []
    try:
        nfo_files = list(root_path.rglob('*.nfo'))
    except OSError:
        nfo_files = []

    for nfo in nfo_files:
        rel = nfo.relative_to(root_path)
        segments = rel.parts
        file_base = nfo.name[: -len('.nfo')]
        if len(segments) == 1:
            entry = LocatedNfo('flat', file_base, nfo, root_path)
            depth = 0
        else:
            if segments[-2] != file_base:
                continue

            entry = LocatedNfo('folder', file_base, nfo, nfo.parent)
            depth = len(segments) - 1

        existing = winners.get(file_base)
        if not existing or existing[1] > depth:
            winners[file_base] = (entry, depth)

    by_basename = {k: v[0] for k, v in winners.items()}
    by_normalized: dict[str, LocatedNfo] = {}
    ambiguous: set[str] = set()
    for base, entry in by_basename.items():
        key = _normalize_basename(base)
        if not key or key in ambiguous:
            continue
        prior = by_normalized.get(key)
        if prior is not None and prior.basename != base:
            del by_normalized[key]
            ambiguous.add(key)
        else:
            by_normalized[key] = entry
    return _CachedIndex(by_basename, by_normalized, root, time.monotonic())


def _get_index(root: str, force_refresh: bool = False) -> _CachedIndex:
    global _cached_index
    with _index_lock:
        now = time.monotonic()
        current = _cached_index if _cached_index is not None and _cached_index.root == root else None
        if current is not None and (now - current.built_at < (_MISS_THROTTLE_S if force_refresh else _INDEX_TTL_S)):
            return current

        _cached_index = _build_index(root)
        return _cached_index


def _lookup(index: _CachedIndex, basename: str) -> LocatedNfo | None:
    hit = index.by_basename.get(basename)
    if hit:
        return hit
    key = _normalize_basename(basename)
    return index.by_normalized.get(key) if key else None


def _locate_nfo(basename: str) -> LocatedNfo | None:
    root = _manual_nfo_root()
    index = _get_index(root)
    hit = _lookup(index, basename)
    if hit:
        return hit

    if time.monotonic() - index.built_at < _MISS_THROTTLE_S:
        return None

    index = _get_index(root, force_refresh=True)
    return _lookup(index, basename)


def _reset_index_cache() -> None:
    global _cached_index
    _cached_index = None


def _txt(v: str | None) -> str | None:
    if v is None:
        return None

    return v.strip() or None


def _repair_xml(text: str) -> str:
    def _amp(m: re.Match[str]) -> str:
        ref = m.group(1)
        if not ref:
            return '&amp;'

        if _XML_ENTITY_RE.match(m.group(0)):
            return m.group(0)

        return html5.get(ref, f'&amp;{ref}')

    text = _AMP_RE.sub(_amp, _BAD_CHAR_RE.sub('', _XML_DECL_RE.sub('', text)))
    return ''.join(c if c != '<' or _TAG_START_RE.match(text, i) else '&lt;' for i, c in enumerate(text))


def _error_context(text: str, err: ET.ParseError) -> str:
    line, col = err.position
    lines = text.splitlines()
    if not 1 <= line <= len(lines):
        return str(err)

    return f'{err} | {lines[line - 1].strip()[:120]!r} (column {col})'


def _parse_xml(raw: bytes, label: str) -> Any:
    try:
        return ET.fromstring(raw)
    except ET.ParseError as err:
        strict_err = err

    text = raw.decode('utf-8', 'replace')
    repaired = _repair_xml(text)
    try:
        root = ET.fromstring(repaired)
    except ET.ParseError:
        try:
            root = lxml_etree.fromstring(repaired.encode('utf-8'), lxml_etree.XMLParser(recover=True))
        except lxml_etree.LxmlError:
            root = None

        if root is None:
            logger.warn('Manual NFO', f'XML parse failed{label}: {_error_context(text, strict_err)}')
            return None

        logger.warn('Manual NFO', f'salvaged malformed XML{label}: {_error_context(text, strict_err)}')
        return root

    logger.warn('Manual NFO', f'repaired malformed XML{label}: {_error_context(text, strict_err)}')
    return root


def _parse_data18(movie: Any) -> str | None:
    row = movie.find('data18')
    if row is None:
        return None

    if ref_id := _txt(row.findtext('id')):
        return f'{_txt(row.findtext("type")) or "scene"}s/{ref_id}'

    return _txt(row.text)


def _parse_nfo(data: bytes | str, label: str = '') -> NfoData | None:
    raw = data.encode('utf-8') if isinstance(data, str) else data
    root = _parse_xml(raw, f' in {label}' if label else '')
    if root is None:
        return None

    movie = root if root.tag == 'movie' else root.find('movie')
    if movie is None:
        return None

    actors: list[dict[str, str]] = []
    for a in movie.findall('actor'):
        name = _txt(a.findtext('name'))
        if not name:
            continue

        actors.append(
            {'name': name, 'role': _txt(a.findtext('role')) or '', 'thumb': _txt(a.findtext('thumb')) or '', 'gender': _txt(a.findtext('gender')) or ''}
        )

    genres = [g for g in (_txt(row.text) for row in movie.findall('genre')) if g]

    fanart_el = movie.find('fanart')
    if fanart_el is not None:
        inner = fanart_el.find('thumb')
        fanart = _txt(inner.text) if inner is not None else _txt(fanart_el.text)
    else:
        fanart = None

    return NfoData(
        title=_txt(movie.findtext('title')) or '',
        genres=genres,
        actors=actors,
        set=_txt(movie.findtext('set')),
        year=_txt(movie.findtext('year')),
        outline=_txt(movie.findtext('outline')),
        plot=_txt(movie.findtext('plot')),
        tagline=_txt(movie.findtext('tagline')),
        release_date=_txt(movie.findtext('releasedate')),
        studio=_txt(movie.findtext('studio')),
        thumb=_txt(movie.findtext('thumb')),
        fanart=fanart,
        data18=_parse_data18(movie),
    )


def _load_and_parse(located: LocatedNfo) -> NfoData | None:
    try:
        data = located.nfo_path.read_bytes()
    except OSError as err:
        logger.warn('Manual NFO', f'read failed {located.nfo_path}: {err}')
        return None

    return _parse_nfo(data, located.nfo_path.name)


def _nfo_release_date(nfo: NfoData) -> str | None:
    if nfo.release_date:
        iso = iso_date(nfo.release_date)
        if iso:
            return iso

    if nfo.year and len(nfo.year) == 4 and nfo.year.isdigit():
        return f'{nfo.year}-01-01'

    return None


def _image_url_for(located: LocatedNfo, filename: str) -> str:
    root = Path(_manual_nfo_root())
    rel_dir = located.sibling_dir.relative_to(root)
    segments = [filename] if str(rel_dir) == '.' else [*rel_dir.parts, filename]
    encoded = '/'.join(quote(s) for s in segments)
    url = f'{config.base_url}/images/manual-nfo/{encoded}'
    return sign_url(url) or url


def _find_sibling_image(located: LocatedNfo, suffix: str) -> str | None:
    for ext in _IMAGE_EXTS:
        if (located.sibling_dir / f'{located.basename}{suffix}{ext}').exists():
            return _image_url_for(located, f'{located.basename}{suffix}{ext}')

    return None


def _is_http(url: str | None) -> bool:
    return bool(url) and (url.startswith('http://') or url.startswith('https://'))  # type: ignore[union-attr]


class ManualNfoClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        tag = search_data.site_info.name
        basename = search_data.title.strip()
        if not basename:
            return

        located = await run_in('fs', _locate_nfo, basename)
        if not located:
            logger.debug(tag, f'search: no NFO for basename="{basename}" under {_manual_nfo_root()}')
            return

        nfo = await run_in('fs', _load_and_parse, located)
        if not nfo:
            return

        title = nfo.title or basename
        thumb = await run_in('fs', _find_sibling_image, located, '-poster')

        results.append(
            build_search_result(
                site=search_data.site_info,
                title=title,
                scene_url=str(located.nfo_path),
                search_url=str(located.nfo_path),
                query=basename,
                display_date=_nfo_release_date(nfo),
                search_date=search_data.search_date,
                score=100,
                cur_id=pack_cur_id([basename]),
                thumb_url=thumb,
            )
        )

    # ── Context Loader ────────────────────────────────────────────────────────

    async def load_scene_context(self, payload: str, site: Any, ctx: SceneContext | None = None) -> LoadedScene | None:
        basename = payload.strip()
        located = await run_in('fs', _locate_nfo, basename)
        if not located:
            logger.warn(site.name, f'loadSceneContext: NFO missing for basename="{basename}"')
            return None

        nfo = await run_in('fs', _load_and_parse, located)
        if not nfo:
            logger.warn(site.name, f'loadSceneContext: NFO parse failed at {located.nfo_path}')
            return None

        return LoadedScene(
            url=str(located.nfo_path),
            site=site,
            scene_date=_nfo_release_date(nfo),
            capture=ctx.capture if ctx else None,
            extra={'located': located, 'nfo': nfo},
        )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _nfo(self, scene: LoadedScene) -> NfoData | None:
        return scene.extra['nfo'] if isinstance(scene.extra, dict) else None

    def _located(self, scene: LoadedScene) -> LocatedNfo | None:
        return scene.extra['located'] if isinstance(scene.extra, dict) else None

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        nfo = self._nfo(scene)

        metadata.title = (nfo.title if nfo else '') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        nfo = self._nfo(scene)
        if not nfo:
            return

        metadata.summary = nfo.plot or nfo.outline or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        nfo = self._nfo(scene)

        metadata.studio = (nfo.studio if nfo else '') or ''

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        nfo = self._nfo(scene)

        metadata.tagline = (nfo.tagline if nfo else '') or ''

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        nfo = self._nfo(scene)

        metadata.collections = [nfo.set] if nfo and nfo.set else None

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        nfo = self._nfo(scene)

        metadata.release_date = _nfo_release_date(nfo) if nfo else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        nfo = self._nfo(scene)

        metadata.genres = (nfo.genres if nfo else None) or []

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        nfo = self._nfo(scene)
        if not nfo:
            return

        out: list[ActorResult] = []
        for a in nfo.actors:
            g = a.get('gender', '').lower().strip()
            thumb = a.get('thumb', '')
            out.append(ActorResult(name=a['name'], photo_url=thumb if _is_http(thumb) else '', gender=g if g in GENDER_SUFFIXES else ''))

        metadata.actors = out

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        nfo = self._nfo(scene)
        located = self._located(scene)
        if not nfo or not located:
            return

        images: list[str] = []
        poster = await run_in('fs', _find_sibling_image, located, '-poster') or (nfo.thumb if _is_http(nfo.thumb) else None)
        if poster:
            images.append(poster)

        fanart = await run_in('fs', _find_sibling_image, located, '-fanart') or (nfo.fanart if _is_http(nfo.fanart) else None)
        if fanart and fanart != poster:
            images.append(fanart)

        if scene.site.scraper_config.data18_enrichment and env.data18_enabled and (nfo.title or nfo.data18):
            forced_url = scene_url_from_ref(nfo.data18)
            if nfo.data18 and not forced_url:
                logger.warn(scene.site.name, f'ignoring unusable <data18> value: {nfo.data18!r}')

            scene_id = slugify(nfo.title.replace("'", '')) if nfo.title else None
            scene_date = _nfo_release_date(nfo)
            providers = [p for p in (nfo.studio, nfo.set) if p]
            title = nfo.title or ''
            await self.enrich_from_data18(
                metadata, scene.site, scene_id=scene_id, providers=providers, title=title, scene_date=scene_date, images=images, forced_url=forced_url
            )

        metadata.art = images


__testing__ = {'locate_nfo': _locate_nfo, 'parse_nfo': _parse_nfo, 'manual_nfo_root': _manual_nfo_root, 'reset_index_cache': _reset_index_cache}
