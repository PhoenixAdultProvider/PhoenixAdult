from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar
from urllib.parse import quote, urljoin, urlsplit

import httpx2
from dateutil import parser as date_parser
from parsel import Selector

from phoenixadult.clients.base import Client
from phoenixadult.config.env import env
from phoenixadult.models.scrape import SearchContext, SearchResult
from phoenixadult.registry import normalize_site_key
from phoenixadult.utils.concurrency import gate
from phoenixadult.utils.concurrency.gate import loop_gate
from phoenixadult.utils.helpers.data18 import (
    DATA18_BASE,
    DATA18_HOSTS,
    Data18Kind,
    data18_ref,
    data18_scene_id,
    manual_mapping_extras,
    manual_mapping_url,
    url_id,
    xp_ns,
)
from phoenixadult.utils.helpers.html_helpers import first_attr, web_search_urls
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.scoring import sceneid_distance_score
from phoenixadult.utils.helpers.search_results import build_search_result
from phoenixadult.utils.helpers.urls import append_unique
from phoenixadult.utils.images.image_classifier import classify_image
from phoenixadult.utils.images.image_fetcher import fetch_dimensions
from phoenixadult.utils.logging.best_effort import best_effort
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.processors.similarity import compare_string
from phoenixadult.utils.processors.title_case import convert_sequence_numbers

_SEARCH_URL_TPL = f'{DATA18_BASE}/sys/live.php?index=&key='
_MAX_ACCURACY = 100.0
_CAST_PREFIX_RE = re.compile(r'^\s*(?:scene|movie)\s+w/\s*', re.IGNORECASE)
_SPECIAL_GALLERIES = {1001, 1101, 1201, 1901}
_MAX_GALLERY_IMAGES = 600
_TITLE_XP = '(//h1)[1]'
_ID_ONLY_RE = re.compile(r'/(?:scenes|movies)/\d+/?$')


@dataclass
class Data18Candidate:
    url: str
    url_id: str
    title_raw: str
    truncated: bool
    provider: str
    release_date: str | None


# ── Scoring ────────────────────────────────────────────────────────────────────


def _similarity(a: str, b: str) -> float:
    if not a and not b:
        return 1.0

    if not a or not b:
        return 0.0

    return compare_string(a, b).dice


def _provider_similarity(a: str | list[str], b: str | list[str]) -> float:
    a_list = [normalize_site_key(x) for x in (a if isinstance(a, list) else [a])]
    b_list = [normalize_site_key(y) for y in (b if isinstance(b, list) else [b])]
    best = 0.0
    for x in a_list:
        for y in b_list:
            best = max(best, _similarity(x, y))

    return best


def _date_gap(a: datetime | None, b: datetime | None) -> float:
    return abs((a - b).total_seconds()) / 86_400 if a and b else float('inf')


def _date_match(a: datetime | None, b: datetime | None, tolerance_days: int = 7) -> int:
    return 1 if _date_gap(a, b) <= tolerance_days else 0


def _name_key(raw: str) -> str:
    return re.sub(r'\W', '', raw).lower()


def _row_cast(a: Selector) -> set[str]:
    for node in a.xpath('.//p[contains(@class,"gen11")]'):
        raw = first_attr(node, 'normalize-space(.)')
        if _CAST_PREFIX_RE.match(raw):
            return {key for key in (_name_key(part) for part in _CAST_PREFIX_RE.sub('', raw).split(',')) if key}

    return set()


def _cast_overlap(wanted: list[str], found: set[str]) -> float:
    keys = {key for key in (_name_key(name) for name in wanted) if key}
    if not keys or not found:
        return 0.0

    return len(keys & found) / len(keys)


@dataclass
class _Ranked:
    url: str
    accuracy: float
    gap: float
    cast: float

    @property
    def rank(self) -> tuple[float, float, float]:
        return (self.accuracy, -self.gap, self.cast)


def _rank_anchor(a: Selector, path_segment: str, query_clean: str, providers: list[str], scene_date: datetime | None, actors: list[str]) -> _Ranked | None:
    href = a.xpath('./@href').get() or ''
    if path_segment not in href:
        return None

    title_node = a.xpath('.//p[contains(@class,"gen12") and contains(@class,"bold")]')
    if not title_node:
        return None

    title_raw = first_attr(title_node[0], 'normalize-space(.)')
    title_clean = re.sub(r'\W', '', title_raw).lower()

    span = a.xpath('.//span[contains(@class,"gen11")]')
    date_raw = _direct_text(span[0]) if span else ''
    search_date = _parse_date(date_raw) if date_raw and date_raw != 'unknown' else None
    provider = first_attr(a, './/span[contains(@class,"gen11")]//i[1]/text()')

    truncated_prefix = title_clean.split('...')[0].strip()
    use_title = not (('...' in title_raw) and truncated_prefix and truncated_prefix in query_clean)
    accuracy = _accuracy_score(
        _ScoreInputs(title=query_clean, date=scene_date, provider=providers), _ScoreInputs(title=title_clean, date=search_date, provider=provider), use_title
    )

    gap = _date_gap(scene_date, search_date)
    cast = _cast_overlap(actors, _row_cast(a))
    logger.debug('data18', f'"{title_clean}" vs "{query_clean}" date="{date_raw}" provider="{provider}" accuracy={accuracy} gap={gap}d cast={cast:.2f}')
    return _Ranked(url=href if href.startswith('http') else f'{DATA18_BASE}{href}', accuracy=accuracy, gap=gap, cast=cast)


@dataclass
class _ScoreInputs:
    title: str
    date: datetime | None
    provider: str | list[str]


def _accuracy_score(a: _ScoreInputs, b: _ScoreInputs, use_title: bool = True) -> float:
    w_date = 0.03 if use_title else 0.5
    w_provider = 0.9 if use_title else 0.5
    w_title = 0.07 if use_title else 0.0
    score = _date_match(a.date, b.date) * w_date
    score += _provider_similarity(a.provider, b.provider) * w_provider
    if use_title:
        score += _similarity(a.title, b.title) * w_title

    return round(score * 100 * 100) / 100


def _parse_date(raw: str) -> datetime | None:
    try:
        parsed: datetime = date_parser.parse(raw)
    except (ValueError, OverflowError):
        return None

    return parsed


def _direct_text(node: Selector) -> str:
    text = ' '.join(node.xpath('text()').getall())
    return re.sub(r'\s+', ' ', text.replace('\xa0', ' ')).strip()


def _clean_thumb(u: str) -> str:
    return u.replace('/th8', '').replace('-th8', '')


class Data18Client(Client):
    default_headers: ClassVar[dict[str, str]] = {'Referer': DATA18_BASE}
    default_cookies: ClassVar[dict[str, str]] = {'data_user_captcha': '1'}

    async def data18_search(
        self,
        search_data: SearchContext,
        results: list[SearchResult],
        *,
        kind: str,
        ws_query: str,
        clean_ws_url: Callable[[str], str | None],
        extract_detail: Callable[[Selector, str], tuple[str, str, str] | None],
        max_pages: int = 10,
    ) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        scene_id = data18_scene_id(search_data.scene_id)
        text = search_data.title.strip()

        urls: set[str] = set()
        if scene_id:
            urls.add(f'{base}/{kind}/{scene_id}')

        candidates: list[Data18Candidate] = []
        with best_effort(search_data.site_info.name, 'find_candidates'):
            candidates = await self.find_candidates(text or search_data.title, kind, max_pages=max_pages)

        with best_effort(search_data.site_info.name, 'webSearch', level='debug'):
            for u in await web_search_urls(ws_query, search_data.site_info):
                if cleaned := clean_ws_url(u):
                    urls.add(cleaned)

        seen: set[str] = set()

        for c in candidates:
            if c.url in seen:
                continue

            seen.add(c.url)
            urls.discard(c.url)
            title = c.title_raw
            if c.truncated:
                loaded = await self.fetch_page(c.url)
                if loaded is not None:
                    title = xp_ns(loaded, _TITLE_XP) or title

            score = sceneid_distance_score(scene_id, c.url_id) if scene_id else None

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=c.url,
                    query=text or search_data.title,
                    display_date=c.release_date,
                    search_date=search_data.search_date,
                    score=score,
                    cur_id=pack_cur_id([p for p in (c.url, c.release_date) if p]),
                    subsite=c.provider or None,
                )
            )

        for url in urls:
            if url in seen:
                continue

            seen.add(url)
            loaded = await self.fetch_page(url)
            if loaded is None:
                continue

            detail = extract_detail(loaded, url)
            if detail is None:
                continue

            title, release_date, subsite = detail
            score = sceneid_distance_score(scene_id, url_id(url)) if scene_id else None

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=url,
                    query=text or search_data.title,
                    display_date=release_date or None,
                    search_date=search_data.search_date,
                    score=score,
                    cur_id=pack_cur_id([p for p in (url, release_date) if p]),
                    subsite=subsite or None,
                )
            )

    async def _fetch_search_page(self, clean_query: str, page: int) -> tuple[str, Selector] | None:
        url = f'{_SEARCH_URL_TPL}{quote(clean_query)}&key2={quote(clean_query)}&next=1&page={page}'
        search_results = await self.fetch_and_load(url, label=f'[data18] search "{clean_query}" p{page}')
        if not search_results:
            return None

        return search_results['html'], search_results['sel']

    async def find_scene_url(
        self,
        scene_id: str | None,
        query: str,
        providers: list[str],
        scene_date: datetime | None,
        kind: Data18Kind = 'scene',
        search: bool = True,
        actors: list[str] | None = None,
    ) -> str | None:
        logger.debug('data18', f'find_scene_url: scene_id={scene_id} query="{query}" providers={providers} scene_date={scene_date} kind={kind}')
        if forced := manual_mapping_url(scene_id):
            return forced

        if not search:
            logger.debug('data18', f'search disabled for scene_id={scene_id} — manual mappings only')
            return None

        url = await self._search_scene_url(query, providers, scene_date, kind, actors)
        if not url and (alt := convert_sequence_numbers(query)):
            logger.info('data18', f'no match for "{query}" — retrying as "{alt}"')
            url = await self._search_scene_url(alt, providers, scene_date, kind, actors)

        if not url:
            logger.info('data18', f'no match for "{query}"')

        return url

    async def _search_scene_url(
        self, query: str, providers: list[str], scene_date: datetime | None, kind: Data18Kind = 'scene', actors: list[str] | None = None
    ) -> str | None:
        clean_query = re.sub(r'[^\w\s]', '', query).strip()
        if not clean_query:
            return None

        query_clean = re.sub(r'\W', '', query).lower()
        min_accuracy = env.data18_accuracy
        cast = actors or []

        page_zero = await self._fetch_search_page(clean_query, 0)
        if not page_zero:
            return None

        html, sel = page_zero
        pages_match = re.search(r'pages:\s*(\d+)', html)
        num_pages = min(int(pages_match.group(1)) if pages_match else 1, 150)

        path_segment = f'/{kind}s/'
        best: _Ranked | None = None
        for page in range(num_pages):
            for a in sel.xpath('//a'):
                ranked = _rank_anchor(a, path_segment, query_clean, providers, scene_date, cast)
                if not ranked or ranked.accuracy < min_accuracy:
                    continue

                if best is None or ranked.rank > best.rank:
                    best = ranked

                if ranked.accuracy >= _MAX_ACCURACY and ranked.gap == 0 and (ranked.cast == 1.0 or not cast):
                    return ranked.url

            if page + 1 < num_pages:
                next_page = await self._fetch_search_page(clean_query, page + 1)
                if not next_page:
                    break

                _, sel = next_page

        if best:
            logger.debug('data18', f'best match for "{query_clean}": {best.url} accuracy={best.accuracy} date gap={best.gap}d cast={best.cast:.2f}')

        return best.url if best else None

    async def enrich_images(
        self,
        *,
        scope: str,
        images: list[str],
        scene_id: str | None = None,
        title: str = '',
        providers: list[str] | None = None,
        scene_date: datetime | None = None,
        forced_url: str | None = None,
        kind: Data18Kind = 'scene',
        allow_square: bool = True,
        priority: list[str] | None = None,
        search: bool = True,
        actors: list[str] | None = None,
    ) -> str | None:
        with best_effort(scope, 'data18 enrichment'):
            url = forced_url or await self.find_scene_url(scene_id, title, providers or [], scene_date, kind, search=search, actors=actors)
            if url:
                logger.info(scope, f'data18 enrichment {"manual" if forced_url else "match"}: {url}')
                ref = data18_ref(url)
                for page_url in [url, *manual_mapping_extras(url)]:
                    fetched = await (self.fetch_movie_images(page_url, covers=priority) if ref and ref['type'] == 'movie' else self.fetch_images(page_url))
                    if not allow_square:
                        fetched = await self._drop_square(scope, fetched)

                    for u in fetched:
                        append_unique(images, u)

                return url

        return None

    @staticmethod
    async def _drop_square(scope: str, urls: list[str]) -> list[str]:
        async def is_square(u: str) -> bool:
            dims = await fetch_dimensions(u, [DATA18_BASE])
            return dims is not None and classify_image(dims['width'], dims['height']).orientation == 'square'

        sem = loop_gate('data18-probe', gate.DATA18_PROBE)

        async def gated(u: str) -> bool:
            async with sem:
                return await is_square(u)

        flags = await asyncio.gather(*(gated(u) for u in urls))
        kept = [u for u, square in zip(urls, flags, strict=True) if not square]
        if dropped := len(urls) - len(kept):
            logger.info(scope, f'dropped {dropped} square data18 image(s)')

        return kept

    async def _resolve_id_url(self, url: str) -> str:
        if not _ID_ONLY_RE.search(url):
            return url

        try:
            r = await self.http.get(url, follow_redirects=False)
        except httpx2.HTTPError:
            return url

        loc: str = r.headers.get('location', '')
        if r.status_code in (301, 302, 307, 308) and loc:
            resolved = urljoin(url, loc)
            if (urlsplit(resolved).hostname or '').lower() in DATA18_HOSTS:
                logger.debug('data18', f'resolved {url} -> {resolved}')
                return resolved

        return url

    async def fetch_page(self, url: str) -> Selector | None:
        details_page_elements = await self.fetch_and_load(url, label=f'[data18] {url}')
        if not details_page_elements and (resolved := await self._resolve_id_url(url)) != url:
            details_page_elements = await self.fetch_and_load(resolved, label=f'[data18] {resolved}')

        if not details_page_elements:
            logger.warn('data18', f'page fetch {url} failed - possible IP ban')
            return None

        sel: Selector = details_page_elements['sel']
        return sel

    @staticmethod
    def _thumbs_from_page(sel: Selector) -> list[str]:
        urls: list[str] = []
        urls += [u for u in sel.xpath('//img[@id="photoimg"]/@src').getall() if u]
        urls += [u for u in sel.xpath('//img[contains(@src,"th8")]/@src').getall() if u]
        urls += [u for u in sel.xpath('//img[contains(@data-original,"th8")]/@data-original').getall() if u]
        return urls

    async def fetch_images(self, scene_url: str) -> list[str]:
        out: list[str] = []
        details_page_elements = await self.fetch_and_load(scene_url, label=f'[data18] images {scene_url}')
        if not details_page_elements and (resolved := await self._resolve_id_url(scene_url)) != scene_url:
            scene_url = resolved
            details_page_elements = await self.fetch_and_load(scene_url, label=f'[data18] images {scene_url}')

        if not details_page_elements:
            logger.warn('data18', 'sceneURL fetch failed - possible IP ban')
            return out

        sel = details_page_elements['sel']

        id_match = re.search(r'/scenes/(\d+)', scene_url)
        scene_id = id_match.group(1) if id_match else ''
        scene_prefix = scene_id[:1]
        scene_suffix = scene_id[1:]

        stop_after_photoset = False
        for gallery in sel.xpath('//div[@id="galleriesoff"]//div'):
            if stop_after_photoset:
                break

            id_attr = gallery.xpath('./@id').get() or ''
            try:
                gallery_id = int(id_attr.replace('gallery', ''))
            except ValueError:
                continue

            viewer_url = f'{DATA18_BASE}/sys/media_photos.php?s={scene_prefix}&scene={scene_suffix}&pic={gallery_id}'
            viewer_page_elements = await self.fetch_and_load(viewer_url, label=f'[data18] gallery {gallery_id}')
            if not viewer_page_elements:
                continue

            viewer = viewer_page_elements['sel']

            for img in self._thumbs_from_page(viewer):
                if '/th8_2' in img:
                    continue

                full = _clean_thumb(img)
                if full not in out:
                    out.append(full)

            if gallery_id in _SPECIAL_GALLERIES:
                try:
                    seed = _clean_thumb(viewer.xpath('//img[contains(@src,"th8")]/@src').get() or '')
                    start_num = int(seed.split('/')[-1].split('.')[0])
                    total_text = viewer.xpath('normalize-space(//div[@id="primaryphoto"]//div//b[1])').get() or ''
                    total = min(int(total_text.split('of')[-1].strip()), _MAX_GALLERY_IMAGES)
                    end_num = start_num + (total * 2 if gallery_id == 1101 else total)
                    for idx in range(start_num, end_num):
                        padded = str(idx).zfill(2)
                        if gallery_id == 1901:
                            img = f'{re.sub(r"_2[^_]*$", "", seed)}/t{padded}.jpg'
                        else:
                            img = f'{re.sub(r"/[^/]*$", "", seed)}/{padded}.jpg'

                        if img not in out:
                            out.append(img)

                    if not env.data18_extra_enabled and gallery_id == 1901:
                        stop_after_photoset = True
                except (ValueError, IndexError):
                    pass

        poster = sel.xpath('//div[@id="moviewrap"]//*[@src][1]/@src').get()
        if poster and poster not in out:
            out.append(poster)

        for cover in sel.xpath('//a[@data-lightbox="relatedscenecover"]/@href').getall():
            if cover and cover not in out:
                out.append(cover)

        logger.info('data18', f'Collected {len(out)} image URL(s) from {scene_url}')
        return out

    async def find_candidates(self, query: str, kind: str, max_pages: int = 10) -> list[Data18Candidate]:
        clean_query = re.sub(r'[^\w\s]', '', query).strip()
        if not clean_query:
            return []

        out: list[Data18Candidate] = []
        seen: set[str] = set()
        page_zero = await self._fetch_search_page(clean_query, 0)
        if not page_zero:
            return out

        html, sel = page_zero
        pages_match = re.search(r'pages:\s*(\d+)', html)
        num_pages = min(int(pages_match.group(1)) if pages_match else 1, max_pages)
        path_segment = f'/{kind}/'

        for page in range(num_pages):
            for a in sel.xpath('//a'):
                href = (a.xpath('./@href').get() or '').split('-')[0]
                if path_segment not in href or href in seen:
                    continue

                title_node = a.xpath('.//p[contains(@class,"gen12") and contains(@class,"bold")]')
                if not title_node:
                    continue

                title_raw = first_attr(title_node[0], 'normalize-space(.)')
                provider = first_attr(a, './/span[contains(@class,"gen11")]//i[1]/text()')
                span = a.xpath('.//span[contains(@class,"gen11")]')
                date_raw = _direct_text(span[0]) if span else ''
                release_date = self._iso(_parse_date(date_raw)) if date_raw and date_raw != 'unknown' else None
                url = href if href.startswith('http') else f'{DATA18_BASE}{href}'
                url_id = re.sub(r'.*/', '', href)
                seen.add(href)
                out.append(
                    Data18Candidate(url=url, url_id=url_id, title_raw=title_raw, truncated='...' in title_raw, provider=provider, release_date=release_date)
                )

            if page + 1 < num_pages:
                next_page = await self._fetch_search_page(clean_query, page + 1)
                if not next_page:
                    break

                _, sel = next_page

        return out

    async def fetch_movie_images(self, movie_url: str, page_sel: Selector | None = None, covers: list[str] | None = None) -> list[str]:
        out: list[str] = []
        sel = page_sel
        if sel is None:
            sel = await self.fetch_page(movie_url)
            if sel is None:
                return out

        def add(u: str | None) -> None:
            append_unique(out, u)

        def add_cover(u: str | None) -> None:
            add(u)
            if covers is not None:
                append_unique(covers, u)

        add_cover(sel.xpath('//a[@id="enlargecover"][1]/@data-featherlight').get())
        add_cover(sel.xpath('//img[@id="backcoverzone"][1]/@src').get())
        add_cover(sel.xpath('//img[@id="imgposter"][1]/@src').get())
        for u in sel.xpath('//img[contains(@src,"th8")]/@src').getall():
            add(_clean_thumb(u))

        for u in sel.xpath('//img[contains(@data-original,"th8")]/@data-original').getall():
            add(_clean_thumb(u))

        id_match = re.search(r'/movies/(\d+)', movie_url)
        movie_id = id_match.group(1) if id_match else ''
        movie_prefix = movie_id[1:]
        if movie_prefix:
            gallery_ids = [
                gid for gallery in sel.xpath('//div[@id="galleriesoff"]//div') if (gid := (gallery.xpath('./@id').get() or '').replace('gallery', ''))
            ]
            sem = loop_gate('data18-gallery', gate.DATA18_GALLERY)

            async def viewer_for(gallery_id: str) -> Selector | None:
                async with sem:
                    return await self.fetch_page(f'{DATA18_BASE}/sys/media_photos.php?movie={movie_prefix}&pic={gallery_id}')

            for viewer in await asyncio.gather(*(viewer_for(gid) for gid in gallery_ids)):
                if not viewer:
                    continue

                for u in viewer.xpath('//img[contains(@src,"th8")]/@src').getall():
                    add(_clean_thumb(u))

                for u in viewer.xpath('//img[contains(@data-original,"th8")]/@data-original').getall():
                    add(_clean_thumb(u))

        logger.info('data18', f'Collected {len(out)} movie image URL(s) from {movie_url}')
        return out

    @staticmethod
    def _iso(d: datetime | None) -> str | None:
        return f'{d.year:04d}-{d.month:02d}-{d.day:02d}' if d else None
