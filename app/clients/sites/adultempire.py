from __future__ import annotations

import asyncio
import json
import re
from typing import Any
from urllib.parse import urlsplit

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SearchContext, SearchResult
from app.config.env import env
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import build_search_result, iso_date, load_site_json, pack_cur_id
from app.utils.helpers.html_helpers import first_attr
from app.utils.logging.logger import logger
from app.utils.processors.similarity import compare_string
from app.utils.processors.title_case import title_case
from app.utils.searchengines import SearchOptions, web_search

_SCENE_ACTORS: dict[str, list[str]] = load_site_json(__file__, 'adultempire_scene_actors')
_REFERER = 'http://www.data18.empirestores.co'
_STARRING_ANCHORS = '(//div[contains(.,"Starring")])[1]//a[contains(@label,"Performer") and contains(@href,"/porn-videos/")]'
_CAST_LI = '//div[.//a[@name="cast"]]//li'


def _h1_title(sel: Any) -> str:
    return ''.join(sel.xpath('(//h1)[1]/text()').getall()).strip()


def _release_date(sel: Any) -> str | None:
    nodes = sel.xpath('(//li[contains(.,"Released:")])[1]')
    if not nodes:
        return None
    raw = re.sub(r'.*Released:\s*', '', nodes[0].xpath('string(.)').get() or '', flags=re.S).strip()
    if not raw or raw.lower() == 'unknown':
        return None
    return iso_date(raw, '%b %d %Y') or iso_date(raw)


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
    base_score = 80 - compare_string(search_vol_num, result_vol_num).levenshtein if is_vol_search and result_vol_num else 80
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
    def __init__(self) -> None:
        super().__init__({'Referer': _REFERER})
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
            try:
                await self.http.get(f'{base}/')  # prime: receive the guest etoken cookie
                await self.http.get(f'{base}/Account/AgeConfirmation?ageConfirmationClicked=true')
                logger.debug('AdultEmpire', f'age-confirm handshake done; jar={list(self.http.cookies.keys())}')
            except Exception as err:  # noqa: BLE001 - best-effort; proceed regardless
                logger.debug('AdultEmpire', f'age-confirm handshake failed: {err}')
            self._age_confirmed = True

    async def _load(self, url: str, capture: list[Any] | None, label: str) -> Any | None:
        loaded = await self.fetch_and_load(url, FetchCtx(capture=capture), label)
        if not loaded:
            logger.debug('AdultEmpire', f'_load: fetch returned None for {url}')
            return None
        logger.debug('AdultEmpire', f'_load: HTTP {loaded.get("status")} {len(loaded.get("html") or "")} bytes for {url}')
        return loaded['sel']

    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        name = ctx.site_info.name
        base = ctx.site_info.base_url.rstrip('/')
        await self._ensure_age_confirmed(base)
        direct_id = ctx.scene_id is not None and ctx.scene_id.isdigit() and int(ctx.scene_id) > 100
        scene_id = ctx.scene_id if direct_id and ctx.scene_id else ''
        title_parts = ctx.title.strip().split()
        search_vol_num = re.sub(r'[^0-9a-zA-Z]+', '', title_parts[-1]) if title_parts else ''
        is_vol_search = not direct_id and bool(re.fullmatch(r'\d+', search_vol_num))
        logger.debug(
            name, f'search "{ctx.title}" (direct_id={direct_id}, vol_search={is_vol_search}, token={"set" if env.adult_empire_login_token else "absent"})'
        )

        movie_urls: dict[str, str] = {}  # url -> result_type
        if direct_id:
            movie_urls[f'{base}/{scene_id}'] = ''
        else:
            encoded = re.sub(r'\s+', '+', re.sub(r"[&'#,]", '', ctx.title).split('scene')[0].strip())
            search_url = f'{base}{ctx.site_info.search_path}{encoded}'
            logger.debug(name, f'on-site search URL: {search_url}')
            sel = await self._load(search_url, ctx.capture, f'[{name}] search "{ctx.title}"')
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
            try:
                host = urlsplit(ctx.site_info.base_url).hostname or ''
                web_urls = await web_search(SearchOptions(query=ctx.title, site=host, num=10))
                added = 0
                for u in web_urls:
                    if 'movies' in u and '.html' not in u:
                        url = re.sub(r'/[^/]*$', '', u)
                        if url not in movie_urls:
                            movie_urls[url] = ''
                            added += 1
                logger.debug(name, f'web-search returned {len(web_urls)} URL(s); {added} new movie URL(s)')
            except Exception as err:  # noqa: BLE001 - search failure is non-fatal
                logger.debug(name, f'webSearch threw: {err}')

        logger.debug(name, f'movie URLs to process: {len(movie_urls)}')
        results: list[SearchResult] = []
        for movie_url, result_type in movie_urls.items():
            sel = await self._load(movie_url, ctx.capture, f'[{name}] movie {movie_url}')
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
                search_date=ctx.search_date,
                on_page_date=date,
                query=ctx.title,
                title=title,
            )

            results.append(
                build_search_result(
                    title=_fmt_movie_display(title, studio, result_type, result_vol_num),
                    scene_url=movie_url,
                    query=ctx.title,
                    display_date=date,
                    search_date=ctx.search_date,
                    score=movie_score,
                    cur_id=pack_cur_id([json.dumps({'movieURL': movie_url, 'searchDate': ctx.search_date})]),
                )
            )

            for row in _scene_rows(sel):
                results.append(
                    build_search_result(
                        title=_fmt_split_display(title, row['scene_num'], row['scene_title'], row['actor_names'], studio, result_type),
                        scene_url=movie_url,
                        query=ctx.title,
                        display_date=date,
                        search_date=ctx.search_date,
                        score=100 if direct_hit else movie_score,
                        cur_id=pack_cur_id(
                            [json.dumps({'movieURL': movie_url, 'sceneNum': row['scene_num'], 'sceneIndex': row['scene_index'], 'searchDate': ctx.search_date})]
                        ),
                    )
                )
        logger.debug(name, f'search "{ctx.title}" -> {len(results)} result(s)')
        return results

    # ── Context loader ────────────────────────────────────────────────────────

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

    def _packed(self, scene: LoadedScene) -> dict[str, Any]:
        return scene.extra if isinstance(scene.extra, dict) else {}

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        title = _h1_title(scene.sel)
        if not title:
            return None
        scene_num = self._packed(scene).get('sceneNum')
        return f'{title} [Scene {scene_num}]' if scene_num is not None else title

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        parts = [t for t in (p.xpath('normalize-space(.)').get() or '' for p in scene.sel.xpath('//div[@class="container"][.//h2]//parent::p')) if t]
        return '\n'.join(parts) or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return _studio(scene.sel) or None

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        series = first_attr(scene.sel, '(//h2//a[@label="Series"])[1]/text()')
        if not series:
            return None
        parts = series.split('"')
        if len(parts) < 2:
            return None
        cleaned = re.sub(r'\(.*\)', '', parts[1]).strip()
        return cleaned or None

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        collections: list[str] = []
        studio = _studio(scene.sel)
        if studio:
            collections.append(studio)
        tagline = await self.fetch_tagline(scene)
        if tagline:
            if tagline not in collections:
                collections.append(tagline)
        elif self._packed(scene).get('sceneNum') is not None:
            h1 = _h1_title(scene.sel)
            if h1 and h1 not in collections:
                collections.append(h1)
        return collections or None

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return _release_date(scene.sel)

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//li//a[@label="Category"]')]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        packed = self._packed(scene)
        split_scene = packed.get('sceneNum') is not None
        actors: list[ActorResult] = []
        seen: set[str] = set()

        def add(name: str, photo: str = '') -> None:
            n = name.split('(')[0].strip()
            if n and n not in seen:
                seen.add(n)
                actors.append(ActorResult(name=n, photo_url=photo))

        anchors = scene.sel.xpath(_STARRING_ANCHORS)
        if split_scene:
            rows = scene.sel.xpath('//div[contains(@class,"row")][.//h3]')
            idx = packed.get('sceneIndex') or 0
            if idx < len(rows):
                row_anchors = rows[idx].xpath('.//div/a')
                if row_anchors:
                    anchors = row_anchors

        for a in anchors:
            name = a.xpath('normalize-space(.)').get() or ''
            photo = (scene.sel.xpath(f'(//div[contains(.,"Starring")]//img[contains(@title,"{name.strip()}")]/@src)[1]').get() or '') if name.strip() else ''
            add(name, photo)

        for extra_name in _SCENE_ACTORS.get(re.sub(r'.*/', '', packed.get('movieURL', '')), []):
            add(extra_name)
        return actors

    async def fetch_directors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        directors: list[ActorResult] = []
        seen: set[str] = set()
        for a in scene.sel.xpath(f'{_CAST_LI}[*[contains(.,"Director")]]//a'):
            name = first_attr(a, 'normalize-space(.)')
            if name and name not in seen:
                seen.add(name)
                directors.append(ActorResult(name=name))
        return directors or None

    async def fetch_producers(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        producers: list[ActorResult] = []
        seen: set[str] = set()
        for node in scene.sel.xpath(f'{_CAST_LI}[*[contains(.,"Producer")]]/text()'):
            name = (node.get() or '').strip()
            if name and name not in seen:
                seen.add(name)
                producers.append(ActorResult(name=name))
        return producers or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        images: list[str] = []
        cover = first_attr(scene.sel, '(//div[contains(@class,"boxcover-container")]//a//img/@src)[1]')
        cover_href = first_attr(scene.sel, '(//div[contains(@class,"boxcover-container")]//a/@href)[1]')
        if cover:
            images.append(cover)
        if cover_href:
            images.append(cover_href)

        packed = self._packed(scene)
        rows = scene.sel.xpath('//div[contains(@class,"row")][.//div[contains(@class,"row")] and .//a[@rel="scenescreenshots"]]')
        if packed.get('sceneNum') is not None:
            idx = packed.get('sceneIndex') or 0
            hrefs = rows[idx].xpath('.//a/@href').getall() if idx < len(rows) else []
        else:
            hrefs = rows.xpath('.//div[contains(@class,"row")]//a/@href').getall()
        for href in hrefs:
            h = (href or '').strip()
            if h and h not in images:
                images.append(h)
        return images
