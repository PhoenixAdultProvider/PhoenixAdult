from __future__ import annotations

import asyncio
import json
import re
from typing import Any, ClassVar

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.config.env import env
from phoenixadult.models.scrape import ActorResult, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.data_files import load_data
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, web_search_urls
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result
from phoenixadult.utils.logging.best_effort import best_effort
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.processors.similarity import compare_string
from phoenixadult.utils.processors.title_case import title_case

_SCENE_ACTORS: dict[str, list[str]] = load_data(__file__, 'adultempire_scene_actors')
_REFERER = 'http://www.data18.empirestores.co'
_STARRING_ANCHORS = '(//div[contains(.,"Starring")])[1]//a[contains(@label,"Performer") and contains(@href,"/porn-videos/")]'
_CAST_LI = '//div[.//a[@name="cast"]]//li'


def _h1_title(sel: Any) -> str:
    return ''.join(sel.xpath('(//h1)[1]/text()').getall()).strip()


def _release_date(sel: Any) -> str | None:
    nodes = sel.xpath('(//li[contains(.,"Released:")])[1]')
    if not nodes:
        return None

    date = re.sub(r'.*Released:\s*', '', nodes[0].xpath('string(.)').get() or '', flags=re.S).strip()
    if not date or date.lower() == 'unknown':
        return None

    return iso_date(date, '%b %d %Y') or iso_date(date)


def _result_type_for(href: str) -> str:
    if '-' not in href:
        return ''

    tail = href.split('-')[-1].replace('.html', '')
    return title_case(tail.replace('ray', 'Blu-Ray'))


def _studio(sel: Any) -> str:
    return first_attr(sel, '(//li[contains(.,"Studio:")]//a)[1]/text()')


def _scene_rows(sel: Any) -> list[dict[str, Any]]:
    rows = sel.xpath('//div[contains(@class,"row")][.//h3]')
    seen: set[str] = set()
    kept: list[dict[str, str]] = []
    for row in rows:
        scene_title = first_attr(row, '(.//a)[1]/text()')
        if not scene_title or scene_title in seen:
            continue

        seen.add(scene_title)
        cast = [t for t in (a.xpath('normalize-space(.)').get() or '' for a in row.xpath('.//div/a')) if t]
        actor_names = ', '.join(cast) if cast else scene_title
        kept.append({'scene_title': scene_title, 'actor_names': actor_names})

    out: list[dict[str, Any]] = []
    for i, k in enumerate(kept):
        scene_num = i + 1
        scene_index = scene_num * 2 - 1 if len(rows) > len(kept) else scene_num - 1
        out.append({'scene_num': scene_num, 'scene_index': scene_index, **k})

    return out


def _score_for(
    *,
    is_direct_hit: bool,
    is_vol_search: bool,
    search_vol_num: str,
    result_vol_num: str | None,
    search_date: str | None,
    on_page_date: str | None,
    query: str,
    title: str,
) -> float:
    if is_direct_hit:
        return 100

    base_score = 100 - compare_string(search_vol_num, result_vol_num).levenshtein if is_vol_search and result_vol_num else 100
    if search_date and on_page_date:
        return base_score - compare_string(search_date, on_page_date).levenshtein

    return base_score - compare_string(query.lower(), title.lower()).levenshtein


def _fmt_movie_display(title: str, studio: str, result_type: str, result_vol_num: str | None) -> str:
    st = f' [{studio}]' if studio else ''
    rt = f' [{result_type}]' if result_type else ''
    if result_vol_num:
        tokens = title.split()
        cleaned = ' '.join(tokens[:-1])
        if re.search(r'(Vol|Vol\.)$', cleaned):
            cleaned = ' '.join(cleaned.split()[:-1])

        return re.sub(r'\s+$', '', f'[Vol. {result_vol_num}] {cleaned}{st}{rt}')

    return f'{title}{st}{rt}'


def _fmt_split_display(movie_title: str, scene_num: int, scene_title: str, actor_names: str, studio: str, result_type: str) -> str:
    rt = f'[{result_type}]' if result_type else ''
    ac = f'[{actor_names}]' if actor_names else ''
    st = f'[{studio}]' if studio else ''
    return f'{movie_title}{rt} / #{scene_num} {scene_title}{ac}{st}'


class AdultEmpireClient(Client):
    genres_xpath = '//li//a[@label="Category"]'

    default_headers: ClassVar[dict[str, str]] = {'Referer': _REFERER}

    def __init__(self) -> None:
        super().__init__()
        self._age_confirmed = False
        self._age_lock = asyncio.Lock()

    async def _ensure_age_confirmed(self, base: str) -> None:
        if self._age_confirmed:
            return

        async with self._age_lock:
            if self._age_confirmed:
                return

            token = env.adult_empire_login_token
            if token:
                self.http.cookies.set('etoken', token, domain='www.adultempire.com', path='/')

            with best_effort('AdultEmpire', 'age-confirm handshake', level='debug'):
                await self.http.get(f'{base}/')
                await self.http.get(f'{base}/Account/AgeConfirmation?ageConfirmationClicked=true')
                logger.debug('AdultEmpire', f'age-confirm handshake done; jar={list(self.http.cookies.keys())}')

            self._age_confirmed = True

    async def _load(self, url: str, capture: list[Any] | None, label: str) -> Any | None:
        details_page_elements = await self.fetch_and_load(url, FetchCtx(capture=capture), label)
        if not details_page_elements:
            logger.debug('AdultEmpire', f'_load: fetch returned None for {url}')
            return None

        logger.debug('AdultEmpire', f'_load: HTTP {details_page_elements.get("status")} {len(details_page_elements.get("html") or "")} bytes for {url}')
        return details_page_elements['sel']

    async def _candidate_movie_urls(self, search_data: SearchContext, *, name: str, base: str, direct_id: bool, scene_id: str) -> dict[str, str]:
        movie_urls: dict[str, str] = {}
        if direct_id:
            movie_urls[f'{base}/{scene_id}'] = ''
        else:
            encoded = re.sub(r'\s+', '+', re.sub(r"[&'#,]", '', search_data.title).split('scene')[0].strip())
            search_url = f'{base}{search_data.site_info.search_path}{encoded}'
            logger.debug(name, f'on-site search URL: {search_url}')
            sel = await self._load(search_url, search_data.capture, f'[{name}] search "{search_data.title}"')
            if sel is not None:
                hrefs = sel.xpath('//div[contains(@class,"product-details__item-title")]//a/@href').getall()
                logger.debug(name, f'on-site product-details hrefs: {len(hrefs)}')
                for href in hrefs:
                    parts = href.split('/')
                    url_id = parts[1] if len(parts) > 1 else ''
                    if not url_id:
                        continue

                    url = f'{base}/{url_id}'
                    if url not in movie_urls:
                        movie_urls[url] = _result_type_for(href)

            with best_effort(name, 'webSearch', level='debug'):
                web_urls = await web_search_urls(search_data.title, search_data.site_info)
                added = 0
                for u in web_urls:
                    if 'movies' in u and '.html' not in u:
                        url = re.sub(r'/[^/]*$', '', u)
                        if url not in movie_urls:
                            movie_urls[url] = ''
                            added += 1

                logger.debug(name, f'web-search returned {len(web_urls)} URL(s); {added} new movie URL(s)')
        return movie_urls

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        name = search_data.site_info.name
        base = search_data.site_info.base_url.rstrip('/')
        await self._ensure_age_confirmed(base)
        direct_id = search_data.scene_id is not None and search_data.scene_id.isdigit() and int(search_data.scene_id) > 100
        scene_id = search_data.scene_id if direct_id and search_data.scene_id else ''
        title_parts = search_data.title.strip().split()
        search_vol_num = re.sub(r'[^0-9a-zA-Z]+', '', title_parts[-1]) if title_parts else ''
        is_vol_search = not direct_id and bool(re.fullmatch(r'\d+', search_vol_num))
        logger.debug(
            name,
            f'search "{search_data.title}" (direct_id={direct_id}, vol_search={is_vol_search}, token={"set" if env.adult_empire_login_token else "absent"})',
        )

        movie_urls = await self._candidate_movie_urls(search_data, name=name, base=base, direct_id=direct_id, scene_id=scene_id)
        logger.debug(name, f'movie URLs to process: {len(movie_urls)}')
        for movie_url, result_type in movie_urls.items():
            sel = await self._load(movie_url, search_data.capture, f'[{name}] movie {movie_url}')
            if sel is None:
                continue

            title = _h1_title(sel)
            if not title:
                logger.debug(name, f'movie page had no <h1> title: {movie_url}')
                continue

            url_id = re.sub(r'.*/', '', movie_url)
            date = _release_date(sel)
            studio = _studio(sel)
            direct_hit = scene_id != '' and scene_id == url_id

            result_vol_num: str | None = None
            if is_vol_search:
                tokens = title.split()
                rv = re.sub(r'[^0-9a-zA-Z]+', '', tokens[-1]) if tokens else ''
                if re.fullmatch(r'\d+', rv):
                    result_vol_num = rv

            movie_score = _score_for(
                is_direct_hit=direct_hit,
                is_vol_search=is_vol_search,
                search_vol_num=search_vol_num,
                result_vol_num=result_vol_num,
                search_date=search_data.search_date,
                on_page_date=date,
                query=search_data.title,
                title=title,
            )

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=_fmt_movie_display(title, studio, result_type, result_vol_num),
                    scene_url=movie_url,
                    query=search_data.title,
                    display_date=date,
                    search_date=search_data.search_date,
                    score=movie_score,
                    cur_id=pack_cur_id([json.dumps({'movieURL': movie_url, 'searchDate': search_data.search_date})]),
                )
            )

            for row in _scene_rows(sel):
                results.append(
                    build_search_result(
                        site=search_data.site_info,
                        title=_fmt_split_display(title, row['scene_num'], row['scene_title'], row['actor_names'], studio, result_type),
                        scene_url=movie_url,
                        query=search_data.title,
                        display_date=date,
                        search_date=search_data.search_date,
                        score=100 if direct_hit else movie_score,
                        cur_id=pack_cur_id(
                            [
                                json.dumps(
                                    {
                                        'movieURL': movie_url,
                                        'sceneNum': row['scene_num'],
                                        'sceneIndex': row['scene_index'],
                                        'searchDate': search_data.search_date,
                                    }
                                )
                            ]
                        ),
                    )
                )

        logger.debug(name, f'search "{search_data.title}" -> {len(results)} result(s)')

    # ── Context Loader ────────────────────────────────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        try:
            packed = json.loads(payload)
            if not isinstance(packed, dict):
                packed = {'movieURL': payload}
        except (ValueError, TypeError):
            packed = {'movieURL': payload}

        movie_url = packed.get('movieURL', '')
        await self._ensure_age_confirmed(site.base_url.rstrip('/'))
        sel = await self._load(movie_url, ctx.capture if ctx else None, f'[{site.name}] detail {movie_url}')
        if sel is None:
            return None

        return LoadedScene(url=movie_url, site=site, scene_date=packed.get('searchDate') or None, capture=ctx.capture if ctx else None, sel=sel, extra=packed)

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _tagline_value(self, scene: LoadedScene) -> str:
        details_page_elements = scene.require_sel()

        series = first_attr(details_page_elements, '(//h2//a[@label="Series"])[1]/text()')
        if not series:
            return ''

        parts = series.split('"')
        if len(parts) < 2:
            return ''

        cleaned = re.sub(r'\(.*\)', '', parts[1]).strip()
        return cleaned

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        title = _h1_title(details_page_elements)
        if not title:
            return

        scene_num = scene.extra_or(dict, {}).get('sceneNum')

        metadata.title = f'{title} [Scene {scene_num}]' if scene_num is not None else title

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        parts = [
            t for t in (p.xpath('normalize-space(.)').get() or '' for p in details_page_elements.xpath('//div[@class="container"][.//h2]//parent::p')) if t
        ]

        metadata.summary = '\n'.join(parts) or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.studio = _studio(details_page_elements) or ''

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline_value(scene)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        collections: list[str] = []
        studio = _studio(details_page_elements)
        if studio:
            collections.append(studio)

        tagline = self._tagline_value(scene)
        if tagline:
            if tagline not in collections:
                collections.append(tagline)
        elif scene.extra_or(dict, {}).get('sceneNum') is not None:
            h1 = _h1_title(details_page_elements)
            if h1 and h1 not in collections:
                collections.append(h1)

        metadata.collections = collections or None

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.release_date = _release_date(details_page_elements)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        packed = scene.extra_or(dict, {})
        split_scene = packed.get('sceneNum') is not None
        actors: list[ActorResult] = []
        seen: set[str] = set()

        def add(name: str, photo: str = '') -> None:
            n = name.split('(')[0].strip()
            if n and n not in seen:
                seen.add(n)
                actors.append(ActorResult(name=n, photo_url=photo))

        anchors = details_page_elements.xpath(_STARRING_ANCHORS)
        if split_scene:
            rows = details_page_elements.xpath('//div[contains(@class,"row")][.//h3]')
            idx = packed.get('sceneIndex') or 0
            if idx < len(rows):
                row_anchors = rows[idx].xpath('.//div/a')
                if row_anchors:
                    anchors = row_anchors

        for a in anchors:
            actor_name = a.xpath('normalize-space(.)').get() or ''
            photo = (
                (details_page_elements.xpath(f'(//div[contains(.,"Starring")]//img[contains(@title,"{actor_name.strip()}")]/@src)[1]').get() or '')
                if actor_name.strip() and '"' not in actor_name
                else ''
            )
            add(actor_name, photo)

        for extra_name in _SCENE_ACTORS.get(re.sub(r'.*/', '', packed.get('movieURL', '')), []):
            add(extra_name)

        metadata.actors = actors

    async def fetch_directors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        directors: list[ActorResult] = []
        seen: set[str] = set()
        for director_link in details_page_elements.xpath(f'{_CAST_LI}[*[contains(.,"Director")]]//a'):
            director_name = first_attr(director_link, 'normalize-space(.)')
            if director_name and director_name not in seen:
                seen.add(director_name)
                directors.append(ActorResult(name=director_name))

        metadata.directors = directors or None

    async def fetch_producers(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        producers: list[ActorResult] = []
        seen: set[str] = set()
        for node in details_page_elements.xpath(f'{_CAST_LI}[*[contains(.,"Producer")]]/text()'):
            producer_name = (node.get() or '').strip()
            if producer_name and producer_name not in seen:
                seen.add(producer_name)
                producers.append(ActorResult(name=producer_name))

        metadata.producers = producers or None

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images: list[str] = []
        cover = first_attr(details_page_elements, '(//div[contains(@class,"boxcover-container")]//a//img/@src)[1]')
        cover_href = first_attr(details_page_elements, '(//div[contains(@class,"boxcover-container")]//a/@href)[1]')
        if cover:
            images.append(cover)

        if cover_href:
            images.append(cover_href)

        packed = scene.extra_or(dict, {})
        rows = details_page_elements.xpath('//div[contains(@class,"row")][.//div[contains(@class,"row")] and .//a[@rel="scenescreenshots"]]')
        if packed.get('sceneNum') is not None:
            idx = packed.get('sceneIndex') or 0
            hrefs = rows[idx].xpath('.//a/@href').getall() if idx < len(rows) else []
        else:
            hrefs = rows.xpath('.//div[contains(@class,"row")]//a/@href').getall()

        for href in hrefs:
            h = (href or '').strip()
            if h and h not in images:
                images.append(h)

        metadata.art = images
