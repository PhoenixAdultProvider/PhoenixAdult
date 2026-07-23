from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, TypedDict
from urllib.parse import urljoin, urlsplit

import httpx2
from dateutil import parser as date_parser
from parsel import Selector

from app.clients.base import Client, SearchContext, SearchResult
from app.config.env import env
from app.utils.helpers.helpers import append_unique, build_search_result, pack_cur_id, sceneid_distance_score, slugify
from app.utils.helpers.html_helpers import first_attr
from app.utils.images.image_classifier import classify_image
from app.utils.images.image_fetcher import fetch_dimensions
from app.utils.logging.best_effort import best_effort
from app.utils.logging.logger import logger
from app.utils.processors.similarity import compare_string
from app.utils.processors.title_case import convert_sequence_numbers
from app.utils.searchengines import SearchOptions, web_search

_BASE = 'https://www.data18.com'
_SEARCH_URL_TPL = f'{_BASE}/sys/live.php?index=&key='
_SPECIAL_GALLERIES = {1001, 1101, 1201, 1901}
_TITLE_XP = '(//h1)[1]'


def data18_scene_id(raw: str | None) -> str:
    """The numeric data18 scene/movie id from a client rating-key, or '' when it isn't a usable id."""
    return raw if raw and raw.isdigit() and int(raw) > 100 else ''


Data18Kind = Literal['scene', 'movie']


class ManualMapping(TypedDict):
    slug: str | list[str]
    type: Data18Kind


def _load_manual_mappings(caller_file: str = __file__) -> dict[str, ManualMapping]:
    """Merge data18_manual_mappings.json with every data18_manual_mappings_*.json sibling
    (sorted by name, later files win on a duplicate id)."""
    folder = Path(caller_file).parent / '_data' / 'data18'
    merged: dict[str, ManualMapping] = {}
    for name in ['data18_manual_mappings', *sorted(p.stem for p in folder.glob('data18_manual_mappings_*.json'))]:
        path = folder / f'{name}.json'
        if path.exists():
            merged.update(json.loads(path.read_text(encoding='utf-8')))

    return merged


DATA18_MANUAL_MAPPINGS: dict[str, ManualMapping] = _load_manual_mappings()


def mapping_slug(title: str, sub_site: str | None) -> str | None:
    """The manual-mapping key a client computes for a scene: slugify(title)[-subsite].
    Kept here so the cache can reproduce it from a snapshot for change detection."""
    sid = slugify(title, replacements=[("'", '')])
    if not sid:
        return None

    return f'{sid}-{re.sub(r"\W", "", sub_site).lower()}' if sub_site else sid


def manual_mapping_url(mapping_key: str | None) -> str | None:
    """The data18 scene/movie URL forced for `mapping_key` (a mapping_slug value), else None.
    An entry's slug may be a list when several scenes share one data18 page."""
    if not mapping_key:
        return None

    for d18, entry in DATA18_MANUAL_MAPPINGS.items():
        slug = entry['slug']
        if mapping_key == slug or (isinstance(slug, list) and mapping_key in slug):
            return f'{_BASE}/{"movies" if entry["type"] == "movie" else "scenes"}/{d18}'

    return None


def xp_ns(sel: Any, xpath: str) -> str:
    """normalize-space() of an XPath expression, '' when it matches nothing."""
    return (sel.xpath(f'normalize-space({xpath})').get() or '').strip()


def xp_first_ns(sel: Any, xpaths: tuple[str, ...]) -> str:
    """First non-empty xp_ns() result across xpaths."""
    for xpath in xpaths:
        if value := xp_ns(sel, xpath):
            return value

    return ''


def squash(value: str) -> str:
    """Lower-case with all whitespace removed, for loose display-name comparison."""
    return re.sub(r'\s+', '', value).lower()


def url_id(url: str) -> str:
    """Numeric id from a data18 scene/movie URL, slug tail stripped."""
    return re.sub(r'.*/', '', url).split('-')[0]


_DATA18_REF_RE = re.compile(r'/(scenes|movies)/(\d+)')


def data18_ref(url: str | None) -> dict[str, str] | None:
    """The {type, id} a data18 scene/movie URL points to (type 'scene'/'movie', numeric
    id, slug tail dropped), or None when it isn't a scene/movie URL."""
    if not url:
        return None

    m = _DATA18_REF_RE.search(url)
    if not m:
        return None

    return {'type': 'scene' if m.group(1) == 'scenes' else 'movie', 'id': m.group(2)}


_REPTYLE_SUFFIX_RE = re.compile(r'\s*-\s*Reptyle$', re.IGNORECASE)


def strip_reptyle_suffix(studio: str) -> str:
    """data18 labels the Reptyle networks "TeamSkeet - Reptyle"; the network is the first part."""
    return _REPTYLE_SUFFIX_RE.sub('', studio).strip()


_SCENE_REF_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*$')
_DATA18_HOSTS = ('data18.com', 'www.data18.com')
_ID_ONLY_RE = re.compile(r'/(?:scenes|movies)/\d+/?$')


def scene_url_from_ref(ref: str | None) -> str | None:
    """Scene/movie URL from a hand-written reference (numeric id, slug, 'scenes/<x>', 'movies/<x>',
    or full data18 URL). Bare refs are scenes; None when empty, off-host, or not a plain ref."""
    if not ref:
        return None

    ref = ref.strip()
    if '://' in ref:
        parts = urlsplit(ref)
        if (parts.hostname or '').lower() not in _DATA18_HOSTS:
            return None

        ref = parts.path

    ref = ref.strip('/')
    kind = 'scenes'
    if ref.lower() in ('scenes', 'movies'):
        return None

    if ref.lower().startswith('movies/'):
        kind, ref = 'movies', ref[len('movies/') :].strip('/')
    elif ref.lower().startswith('scenes/'):
        ref = ref[len('scenes/') :].strip('/')

    return f'{_BASE}/{kind}/{ref}' if _SCENE_REF_RE.match(ref) else None


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
    a_list = a if isinstance(a, list) else [a]
    b_list = b if isinstance(b, list) else [b]
    best = 0.0
    for x in a_list:
        for y in b_list:
            best = max(best, _similarity(x, y))

    return best


def _date_match(a: datetime | None, b: datetime | None, tolerance_days: int = 7) -> int:
    if not a or not b:
        return 0

    diff = abs((a - b).total_seconds()) / 86_400
    return 1 if diff <= tolerance_days else 0


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
    def __init__(self) -> None:
        super().__init__({'Referer': _BASE, 'Cookie': 'data_user_captcha=1'})

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
        """Shared scenes/movies search: candidate lookup + web-search url harvest, then per-url detail
        via `extract_detail(sel, url) -> (title, release_date, subsite) | None`; `clean_ws_url` drops hits."""
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
            host = urlsplit(search_data.site_info.base_url).hostname or ''
            for u in await web_search(SearchOptions(query=ws_query, site=host, num=10)):
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
        from urllib.parse import quote

        url = f'{_SEARCH_URL_TPL}{quote(clean_query)}&key2={quote(clean_query)}&next=1&page={page}'
        search_results = await self.fetch_and_load(url, label=f'[data18] search "{clean_query}" p{page}')
        if not search_results:
            return None

        return search_results['html'], search_results['sel']

    async def find_scene_url(
        self, scene_id: str | None, query: str, providers: list[str], scene_date: datetime | None, kind: Data18Kind = 'scene'
    ) -> str | None:
        logger.debug('data18', f'find_scene_url: scene_id={scene_id} query="{query}" providers={providers} scene_date={scene_date} kind={kind}')
        if forced := manual_mapping_url(scene_id):
            return forced

        url = await self._search_scene_url(query, providers, scene_date, kind)
        if not url and (alt := convert_sequence_numbers(query)):
            logger.info('data18', f'no match for "{query}" — retrying as "{alt}"')
            url = await self._search_scene_url(alt, providers, scene_date, kind)

        if not url:
            logger.info('data18', f'no match for "{query}"')

        return url

    async def _search_scene_url(self, query: str, providers: list[str], scene_date: datetime | None, kind: Data18Kind = 'scene') -> str | None:
        clean_query = re.sub(r'[^\w\s]', '', query).strip()
        if not clean_query:
            return None

        query_clean = re.sub(r'\W', '', query).lower()
        min_accuracy = env.data18_accuracy

        page_zero = await self._fetch_search_page(clean_query, 0)
        if not page_zero:
            return None

        html, sel = page_zero
        pages_match = re.search(r'pages:\s*(\d+)', html)
        num_pages = min(int(pages_match.group(1)) if pages_match else 1, 150)

        path_segment = f'/{kind}s/'
        for page in range(num_pages):
            for a in sel.xpath('//a'):
                href = a.xpath('./@href').get() or ''
                if path_segment not in href:
                    continue

                title_node = a.xpath('.//p[contains(@class,"gen12") and contains(@class,"bold")]')
                if not title_node:
                    continue

                title_raw = first_attr(title_node[0], 'normalize-space(.)')
                title_clean = re.sub(r'\W', '', title_raw).lower()

                span = a.xpath('.//span[contains(@class,"gen11")]')
                date_raw = _direct_text(span[0]) if span else ''
                search_date = _parse_date(date_raw) if date_raw and date_raw != 'unknown' else None
                provider = first_attr(a, './/span[contains(@class,"gen11")]//i[1]/text()')

                network_data = _ScoreInputs(title=query_clean, date=scene_date, provider=providers)
                data18_data = _ScoreInputs(title=title_clean, date=search_date, provider=provider)
                truncated_prefix = title_clean.split('...')[0].strip()
                use_title = not (('...' in title_raw) and truncated_prefix and truncated_prefix in query_clean)
                accuracy = _accuracy_score(network_data, data18_data, use_title)

                logger.debug('data18', f'"{title_clean}" vs "{query_clean}" date="{date_raw}" provider="{provider}" accuracy={accuracy}')
                if accuracy >= min_accuracy:
                    return href if href.startswith('http') else f'{_BASE}{href}'

            if page + 1 < num_pages:
                next_page = await self._fetch_search_page(clean_query, page + 1)
                if not next_page:
                    break

                _, sel = next_page

        return None

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
    ) -> str | None:
        """Resolve a scene's data18 page (forced URL, manual mapping, or search), append its images to
        `images` in place, return the resolved URL; best_effort so a failure never breaks the host scrape."""
        with best_effort(scope, 'data18 enrichment'):
            url = forced_url or await self.find_scene_url(scene_id, title, providers or [], scene_date, kind)
            if url:
                logger.info(scope, f'data18 enrichment {"manual" if forced_url else "match"}: {url}')
                ref = data18_ref(url)
                fetched = await (self.fetch_movie_images(url) if ref and ref['type'] == 'movie' else self.fetch_images(url))
                if not allow_square:
                    fetched = await self._drop_square(scope, fetched)

                for u in fetched:
                    append_unique(images, u)

                return url

        return None

    @staticmethod
    async def _drop_square(scope: str, urls: list[str]) -> list[str]:
        async def is_square(u: str) -> bool:
            dims = await fetch_dimensions(u, [_BASE])
            return dims is not None and classify_image(dims['width'], dims['height']).orientation == 'square'

        flags = await asyncio.gather(*(is_square(u) for u in urls))
        kept = [u for u, square in zip(urls, flags, strict=True) if not square]
        if dropped := len(urls) - len(kept):
            logger.info(scope, f'dropped {dropped} square data18 image(s)')

        return kept

    async def _resolve_id_url(self, url: str) -> str:
        """data18 301s bare id URLs to their slug form but can 403 clients that follow the
        redirect; hop it manually so the slug URL can be fetched directly."""
        if not _ID_ONLY_RE.search(url):
            return url

        try:
            r = await self.http.get(url, follow_redirects=False)
        except httpx2.HTTPError:
            return url

        loc: str = r.headers.get('location', '')
        if r.status_code in (301, 302, 307, 308) and loc:
            resolved = urljoin(url, loc)
            if (urlsplit(resolved).hostname or '').lower() in _DATA18_HOSTS:
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

            viewer_url = f'{_BASE}/sys/media_photos.php?s={scene_prefix}&scene={scene_suffix}&pic={gallery_id}'
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
                    total = int(total_text.split('of')[-1].strip())
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
                url = href if href.startswith('http') else f'{_BASE}{href}'
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

    async def fetch_movie_images(self, movie_url: str, page_sel: Selector | None = None) -> list[str]:
        out: list[str] = []
        sel = page_sel
        if sel is None:
            sel = await self.fetch_page(movie_url)
            if sel is None:
                return out

        def add(u: str | None) -> None:
            append_unique(out, u)

        add(sel.xpath('//a[@id="enlargecover"][1]/@data-featherlight').get())
        add(sel.xpath('//img[@id="backcoverzone"][1]/@src').get())
        add(sel.xpath('//img[@id="imgposter"][1]/@src').get())
        for u in sel.xpath('//img[contains(@src,"th8")]/@src').getall():
            add(_clean_thumb(u))

        for u in sel.xpath('//img[contains(@data-original,"th8")]/@data-original').getall():
            add(_clean_thumb(u))

        id_match = re.search(r'/movies/(\d+)', movie_url)
        movie_id = id_match.group(1) if id_match else ''
        movie_prefix = movie_id[1:]
        if movie_prefix:
            for gallery in sel.xpath('//div[@id="galleriesoff"]//div'):
                gallery_id = (gallery.xpath('./@id').get() or '').replace('gallery', '')
                if not gallery_id:
                    continue

                viewer = await self.fetch_page(f'{_BASE}/sys/media_photos.php?movie={movie_prefix}&pic={gallery_id}')
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
