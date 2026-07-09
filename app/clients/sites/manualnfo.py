from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote
from xml.etree import ElementTree as ET

from app.clients.aggregators.data18 import Data18Client, scene_url_from_ref
from app.clients.base import ActorResult, Client, LoadedScene, SceneContext, SearchContext, SearchResult
from app.config import config
from app.config.env import env
from app.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id, slugify
from app.utils.logging.best_effort import best_effort
from app.utils.logging.logger import logger

_IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.webp')
_INDEX_TTL_S = 60.0
_MISS_THROTTLE_S = 2.0
_ALLOWED_GENDERS = {'male', 'female', 'trans'}


@dataclass
class LocatedNfo:
    layout: str  # 'folder' | 'flat'
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
    data18: str | None = None  # explicit data18 scene ref; bypasses the data18 search


@dataclass
class _CachedIndex:
    by_basename: dict[str, LocatedNfo]
    root: str
    built_at: float


_cached_index: _CachedIndex | None = None
_last_build_started = 0.0


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
    return _CachedIndex({k: v[0] for k, v in winners.items()}, root, time.monotonic())


def _get_index(root: str, force_refresh: bool = False) -> _CachedIndex:
    global _cached_index, _last_build_started
    now = time.monotonic()
    fresh = _cached_index is not None and _cached_index.root == root and now - _cached_index.built_at < _INDEX_TTL_S
    if fresh and not force_refresh:
        assert _cached_index is not None
        return _cached_index
    if force_refresh and _cached_index is not None and _cached_index.root == root and now - _last_build_started < _MISS_THROTTLE_S:
        return _cached_index
    _last_build_started = now
    _cached_index = _build_index(root)
    return _cached_index


def _locate_nfo(basename: str) -> LocatedNfo | None:
    root = _manual_nfo_root()
    index = _get_index(root)
    hit = index.by_basename.get(basename)
    if hit:
        return hit
    index = _get_index(root, force_refresh=True)
    return index.by_basename.get(basename)


def _reset_index_cache() -> None:
    global _cached_index, _last_build_started
    _cached_index = None
    _last_build_started = 0.0


def _txt(v: str | None) -> str | None:
    if v is None:
        return None
    return v.strip() or None


def _parse_nfo(data: bytes | str) -> NfoData | None:
    raw = data.encode('utf-8') if isinstance(data, str) else data
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as err:
        logger.warn('Manual NFO', f'XML parse failed: {err}')
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

    genres = [g for g in (_txt(el.text) for el in movie.findall('genre')) if g]

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
        data18=_txt(movie.findtext('data18')),
    )


def _load_and_parse(located: LocatedNfo) -> NfoData | None:
    try:
        data = located.nfo_path.read_bytes()
    except OSError as err:
        logger.warn('Manual NFO', f'read failed {located.nfo_path}: {err}')
        return None
    return _parse_nfo(data)


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
    return f'{config.base_url}/images/manual-nfo/{encoded}'


def _find_sibling_image(located: LocatedNfo, suffix: str) -> str | None:
    for ext in _IMAGE_EXTS:
        if (located.sibling_dir / f'{located.basename}{suffix}{ext}').exists():
            return _image_url_for(located, f'{located.basename}{suffix}{ext}')
    return None


def _is_http(url: str | None) -> bool:
    return bool(url) and (url.startswith('http://') or url.startswith('https://'))  # type: ignore[union-attr]


class ManualNfoClient(Client):
    def __init__(self) -> None:
        super().__init__()
        self._data18: Data18Client | None = None

    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        tag = ctx.site_info.name
        basename = ctx.title.strip()
        if not basename:
            return []
        located = _locate_nfo(basename)
        if not located:
            logger.debug(tag, f'search: no NFO for basename="{basename}" under {_manual_nfo_root()}')
            return []
        nfo = _load_and_parse(located)
        if not nfo:
            return []
        title = nfo.title or basename
        thumb = _find_sibling_image(located, '-poster')
        return [
            build_search_result(
                title=title,
                scene_url=str(located.nfo_path),
                search_url=str(located.nfo_path),
                query=basename,
                display_date=_nfo_release_date(nfo),
                search_date=ctx.search_date,
                score=100,
                cur_id=pack_cur_id([basename]),
                thumb_url=thumb,
            )
        ]

    # ── Context loader ────────────────────────────────────────────────────────

    async def load_scene_context(self, payload: str, site: Any, ctx: SceneContext | None = None) -> LoadedScene | None:
        basename = payload.strip()
        located = _locate_nfo(basename)
        if not located:
            logger.warn(site.name, f'loadSceneContext: NFO missing for basename="{basename}"')
            return None
        nfo = _load_and_parse(located)
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

    def _nfo(self, scene: LoadedScene) -> NfoData | None:
        return scene.extra['nfo'] if isinstance(scene.extra, dict) else None

    def _located(self, scene: LoadedScene) -> LocatedNfo | None:
        return scene.extra['located'] if isinstance(scene.extra, dict) else None

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        nfo = self._nfo(scene)
        return (nfo.title if nfo else '') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        nfo = self._nfo(scene)
        if not nfo:
            return None
        return nfo.plot or nfo.outline or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        nfo = self._nfo(scene)
        return (nfo.studio if nfo else None) or None

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        nfo = self._nfo(scene)
        return (nfo.tagline if nfo else None) or None

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        nfo = self._nfo(scene)
        return _nfo_release_date(nfo) if nfo else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        nfo = self._nfo(scene)
        return nfo.genres if nfo else None

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        nfo = self._nfo(scene)
        return [nfo.set] if nfo and nfo.set else None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        nfo = self._nfo(scene)
        if not nfo:
            return None
        out: list[ActorResult] = []
        for a in nfo.actors:
            g = a.get('gender', '').lower().strip()
            thumb = a.get('thumb', '')
            out.append(ActorResult(name=a['name'], photo_url=thumb if _is_http(thumb) else '', gender=g if g in _ALLOWED_GENDERS else ''))
        return out

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        nfo = self._nfo(scene)
        located = self._located(scene)
        if not nfo or not located:
            return None
        images: list[str] = []
        poster = _find_sibling_image(located, '-poster') or (nfo.thumb if _is_http(nfo.thumb) else None)
        fanart = _find_sibling_image(located, '-fanart') or (nfo.fanart if _is_http(nfo.fanart) else None)
        if poster:
            images.append(poster)
        if fanart and fanart != poster:
            images.append(fanart)

        if scene.site.scraper_config.data18_enrichment and env.data18_enabled and (nfo.title or nfo.data18):
            with best_effort(scene.site.name, 'data18 enrichment'):
                forced_url = scene_url_from_ref(nfo.data18)
                if nfo.data18 and not forced_url:
                    logger.warn(scene.site.name, f'ignoring unusable <data18> value: {nfo.data18!r}')
                self._data18 = self._data18 or Data18Client()
                data18_url = forced_url
                if not data18_url and nfo.title:
                    date_iso = _nfo_release_date(nfo)
                    date_obj = datetime.fromisoformat(date_iso) if date_iso else None
                    providers = [p for p in (nfo.studio, nfo.set) if p]
                    data18_url = await self._data18.find_scene_url(slugify(nfo.title.replace("'", '')), nfo.title, providers, date_obj)
                if data18_url:
                    logger.info(scene.site.name, f'data18 enrichment {"manual" if forced_url else "match"}: {data18_url}')
                    for u in await self._data18.fetch_images(data18_url):
                        if u not in images:
                            images.append(u)
        return images


__testing__ = {'locate_nfo': _locate_nfo, 'parse_nfo': _parse_nfo, 'manual_nfo_root': _manual_nfo_root, 'reset_index_cache': _reset_index_cache}
