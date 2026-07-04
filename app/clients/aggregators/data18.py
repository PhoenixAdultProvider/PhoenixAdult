from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

import httpx2
from dateutil import parser as date_parser
from parsel import Selector

from app.config.env import env
from app.utils.helpers.html_helpers import first_attr
from app.utils.logging.logger import logger
from app.utils.processors.similarity import compare_string
from app.utils.processors.title_case import convert_sequence_numbers

_BASE = 'https://www.data18.com'
_SEARCH_URL_TPL = f'{_BASE}/sys/live.php?index=&key='
_SPECIAL_GALLERIES = {1001, 1101, 1201, 1901}
_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'

# Ported verbatim from networkReptyle.py:data18ManualMappings (functional config).
DATA18_MANUAL_MAPPINGS: dict[str, str] = {
    '169646': 'thats-better-than-stealing-it-herfreshmanyear',
    '1313219': 'delicious-firsts-hussiepass',
    '1349311': 'thanksgiving-the-hijab-way-hijabhookups',
    '1341218': 'the-vamp-next-door-momswap',
    '1341212': 'home-for-the-holidays-momswap',
}


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


class Data18Client:
    def __init__(self) -> None:
        self._http: httpx2.AsyncClient | None = None

    @property
    def http(self) -> httpx2.AsyncClient:
        if self._http is None:
            self._http = httpx2.AsyncClient(
                timeout=15.0,
                verify=False,
                follow_redirects=True,
                headers={'User-Agent': _UA, 'Referer': _BASE, 'Cookie': 'data_user_captcha=1'},
            )
        return self._http

    async def _fetch_search_page(self, clean_query: str, page: int) -> tuple[str, Selector]:
        from urllib.parse import quote

        url = f'{_SEARCH_URL_TPL}{quote(clean_query)}&key2={quote(clean_query)}&next=1&page={page}'
        html = (await self.http.get(url)).text
        return html, Selector(text=html)

    async def find_scene_url(self, scene_id: str | None, query: str, providers: list[str], scene_date: datetime | None) -> str | None:
        if scene_id and scene_id in DATA18_MANUAL_MAPPINGS:
            return f'{_BASE}/scenes/{DATA18_MANUAL_MAPPINGS[scene_id]}'

        url = await self._search_scene_url(query, providers, scene_date)
        if not url and (alt := convert_sequence_numbers(query)):
            logger.info('data18', f'no match for "{query}" — retrying as "{alt}"')
            url = await self._search_scene_url(alt, providers, scene_date)
        if not url:
            logger.info('data18', f'no match for "{query}"')
        return url

    async def _search_scene_url(self, query: str, providers: list[str], scene_date: datetime | None) -> str | None:
        clean_query = re.sub(r'[^\w\s]', '', query).strip()
        if not clean_query:
            return None
        query_clean = re.sub(r'\W', '', query).lower()
        min_accuracy = env.data18_accuracy

        html, sel = await self._fetch_search_page(clean_query, 0)
        pages_match = re.search(r'pages:\s*(\d+)', html)
        num_pages = min(int(pages_match.group(1)) if pages_match else 1, 50)

        for page in range(num_pages):
            for a in sel.xpath('//a'):
                href = a.xpath('./@href').get() or ''
                if '/scenes/' not in href:
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
                _, sel = await self._fetch_search_page(clean_query, page + 1)

        return None

    async def fetch_page(self, url: str) -> Selector | None:
        try:
            r = await self.http.get(url)
            if r.status_code >= 400:
                return None
            return Selector(text=r.text)
        except httpx2.HTTPError as err:
            logger.warn('data18', f'page fetch {url} failed ({err}) - possible IP ban')
            return None

    @staticmethod
    def _thumbs_from_page(sel: Selector) -> list[str]:
        urls: list[str] = []
        urls += [u for u in sel.xpath('//img[@id="photoimg"]/@src').getall() if u]
        urls += [u for u in sel.xpath('//img[contains(@src,"th8")]/@src').getall() if u]
        urls += [u for u in sel.xpath('//img[contains(@data-original,"th8")]/@data-original').getall() if u]
        return urls

    async def fetch_images(self, scene_url: str) -> list[str]:
        out: list[str] = []
        try:
            html = (await self.http.get(scene_url)).text
        except httpx2.HTTPError as err:
            logger.warn('data18', f'sceneURL fetch failed ({err}) - possible IP ban')
            return out
        sel = Selector(text=html)

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
            try:
                viewer_html = (await self.http.get(viewer_url)).text
            except httpx2.HTTPError:
                continue
            viewer = Selector(text=viewer_html)

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
        logger.info('data18', f'Collected {len(out)} image URL(s) from {scene_url}')
        return out

    async def find_candidates(self, query: str, kind: str, max_pages: int = 10) -> list[Data18Candidate]:
        clean_query = re.sub(r'[^\w\s]', '', query).strip()
        if not clean_query:
            return []

        out: list[Data18Candidate] = []
        seen: set[str] = set()
        html, sel = await self._fetch_search_page(clean_query, 0)
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
                _, sel = await self._fetch_search_page(clean_query, page + 1)

        return out

    async def fetch_movie_images(self, movie_url: str, page_sel: Selector | None = None) -> list[str]:
        out: list[str] = []
        sel = page_sel
        if sel is None:
            sel = await self.fetch_page(movie_url)
            if sel is None:
                return out

        def add(u: str | None) -> None:
            if u and u not in out:
                out.append(u)

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
