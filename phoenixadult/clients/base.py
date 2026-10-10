from __future__ import annotations

import asyncio
import json
from abc import ABC
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Protocol
from urllib.parse import urlencode

import httpx2
from parsel import Selector

from phoenixadult.config.env import env
from phoenixadult.models.capture import RawCaptureEntry
from phoenixadult.models.scrape import ActorResult, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text, web_search_urls
from phoenixadult.utils.helpers.ids import b64url_decode, b64url_encode, pack_cur_id, same_scene
from phoenixadult.utils.helpers.search_results import build_search_result
from phoenixadult.utils.helpers.urls import absolute_url
from phoenixadult.utils.http.bypass import bypass_get, bypass_post, is_challenge, site_backends
from phoenixadult.utils.http.client import make_http
from phoenixadult.utils.http.rate_limit_helper import FAST_GATE, ScenePacer
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.logging.response_trace import trace_body, trace_response

if TYPE_CHECKING:
    from phoenixadult.registry import ResolvedSiteInfo


class Enricher(Protocol):
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
        kind: Any = 'scene',
        allow_square: bool = True,
        priority: list[str] | None = None,
        search: bool = True,
        actors: list[str] | None = None,
    ) -> str | None: ...


_enricher_factory: Callable[[], Enricher] | None = None


def set_enricher_factory(factory: Callable[[], Enricher]) -> None:
    global _enricher_factory
    _enricher_factory = factory


# ── Loaded Contexts Handed to the Per-Field Hooks ─────────────────────────────


@dataclass
class LoadedScene:
    url: str
    site: ResolvedSiteInfo
    scene_date: str | None = None
    fallback_title: str | None = None
    capture: list[RawCaptureEntry] | None = None
    extra: Any = None
    sel: Selector | None = None
    html: str | None = None
    art_referer: str | None = None
    art_cookie: str | None = None
    data18_url: str | None = None
    subsite: str | None = None
    source_kind: str | None = None
    source_json: Any | None = None
    language: str | None = None

    def require_sel(self) -> Selector:
        if self.sel is None:
            raise ValueError(f'{self.url}: scene has no parsed HTML')
        return self.sel

    def require_extra[T](self, kind: type[T]) -> T:
        if not isinstance(self.extra, kind):
            raise ValueError(f'{self.url}: scene extra is {type(self.extra).__name__}, not {kind.__name__}')
        return self.extra

    def extra_or[T](self, kind: type[T], default: T) -> T:
        return self.extra if isinstance(self.extra, kind) else default


@dataclass
class LoadedSearch:
    ctx: SearchContext
    site: ResolvedSiteInfo
    sources: list[Any]
    capture: list[RawCaptureEntry] | None = None
    sel: Selector | None = None
    extra: Any = None


@dataclass
class CandidatePage:
    url: str
    sel: Selector
    html: str


@dataclass
class FetchCtx:
    capture: list[RawCaptureEntry] | None = None
    headers: dict[str, str] | None = None


_CHALLENGE_PAGE_MAX = 16_000


def _challenge_page(body: str) -> bool:
    return len(body) <= _CHALLENGE_PAGE_MAX and is_challenge(body)


def _fallback_enabled() -> bool:
    return env.bypass_auto_retry


# ── Base Client ───────────────────────────────────────────────────────────────


@dataclass(slots=True)
class ImageCollector:
    clean: Any = None
    items: list[str] = field(default_factory=list)

    def push(self, raw: str | None) -> None:
        if not raw:
            return
        url = self.clean(raw) if self.clean else raw
        if url and url not in self.items:
            self.items.append(url)


class Client(ABC):  # noqa: B024 - abstract by intent; subclasses override hooks, none are mandatory
    scraper_type: ClassVar[str] = ''
    default_headers: ClassVar[dict[str, str]] = {}
    default_cookies: ClassVar[dict[str, str]] = {}
    packed_scene_tail: ClassVar[bool] = False

    def __init__(self, extra_headers: dict[str, str] | None = None) -> None:
        self._extra_headers = {**self.default_headers, **(extra_headers or {})}
        self._http: httpx2.AsyncClient | None = None
        self._data18_enricher: Enricher | None = None
        self.pacer: ScenePacer | None = None

    @property
    def http(self) -> httpx2.AsyncClient:
        if self._http is None:
            self._http = make_http(self._extra_headers, cookies=self.default_cookies or None)
        return self._http

    async def aclose(self) -> None:
        if isinstance(self._data18_enricher, Client):
            await self._data18_enricher.aclose()
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    def encode(self, s: str) -> str:
        return b64url_encode(s)

    def decode(self, s: str) -> str:
        return b64url_decode(s)

    def tag(self, site: ResolvedSiteInfo) -> str:
        return site.name

    def studio_for(self, site: ResolvedSiteInfo) -> str | None:
        return None

    # ── Fetch Helpers ──────────────────────────────────────────────────────────

    async def fetch_and_load(
        self, url: str, ctx: FetchCtx | None = None, label: str | None = None, form: dict[str, str] | None = None
    ) -> dict[str, Any] | None:
        verb = 'POST' if form is not None else 'GET'
        direct = None
        if not site_backends(url):
            direct = await self._direct_fetch(url, ctx.headers if ctx else None, form)
            if direct and direct['ok']:
                return {'status': direct['status'], 'html': direct['body'], 'sel': Selector(text=direct['body'])}
            if not _fallback_enabled():
                if direct:
                    logger.debug(f'fetch_and_load {url} → HTTP {direct["status"]}')
                else:
                    logger.warn('scrape', f'fetch_and_load {verb} {url} got nothing back, so there is no page to parse or dump')
                return None
        headers = (ctx.headers if ctx else None) or {}
        if form is not None:
            bypass = await bypass_post(url, urlencode(form), {'Content-Type': 'application/x-www-form-urlencoded', **headers})
        else:
            bypass = await bypass_get(url, headers)
        if not bypass or bypass.status >= 400:
            direct_status = direct['status'] if direct else ('skipped' if site_backends(url) else 'error')
            logger.warn(f'fetch_and_load {url} failed — direct HTTP {direct_status}, bypass status={bypass.status if bypass else "none"}')
            return None
        logger.info(f'fetch_and_load {url} → served via bypass ({bypass.status})')
        trace_body(f'{verb} {url} (bypass)', bypass.status, bypass.body, 'text/html')
        return {'status': bypass.status, 'html': bypass.body, 'sel': Selector(text=bypass.body)}

    async def fetch_json(self, url: str, ctx: FetchCtx | None = None, headers: dict[str, str] | None = None, label: str | None = None) -> Any | None:
        if not site_backends(url):
            try:
                r = await self.http.get(url, headers=headers)
                trace_response(r)
                if r.status_code < 400:
                    data = r.json()
                    return data
                logger.debug(f'fetch_json {url} → HTTP {r.status_code}')
            except (httpx2.HTTPError, ValueError) as err:
                logger.debug(f'fetch_json {url} threw: {err}')
            if not _fallback_enabled():
                return None
        bypass = await bypass_get(url, headers or {})
        if not bypass or bypass.status >= 400:
            logger.warn(f'fetch_json {url} failed — direct and bypass exhausted (bypass status={bypass.status if bypass else "none"})')
            return None
        try:
            parsed = json.loads(bypass.body)
        except ValueError as err:
            logger.debug(f"fetch_json {url} → bypass body wasn't JSON: {err}")
            return None
        logger.info(f'fetch_json {url} → served via bypass ({bypass.status})')
        trace_body(f'GET {url} (bypass)', bypass.status, bypass.body, 'application/json')
        return parsed

    async def _direct_fetch(self, url: str, headers: dict[str, str] | None = None, form: dict[str, str] | None = None) -> dict[str, Any] | None:
        verb = 'POST' if form is not None else 'GET'
        try:
            r = await (self.http.post(url, data=form, headers=headers) if form is not None else self.http.get(url, headers=headers))
            trace_response(r)
            ok = r.status_code < 400 and r.status_code != 202 and bool(r.text.strip()) and not _challenge_page(r.text)
            return {'ok': ok, 'status': r.status_code, 'body': r.text}
        except httpx2.HTTPError as err:
            logger.debug(f'{verb} {url} never returned a response: {type(err).__name__}: {err}')
            return None
        except Exception as err:  # noqa: BLE001 - one unreachable page must not end the whole search
            logger.warn('scrape', f'{verb} {url} raised before a response arrived: {err!r}')
            return None

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        loaded = await self.load_search_context(search_data)
        if not loaded:
            return
        seen = {same_scene(r.scene_url) for r in results if r.scene_url}
        built: list[SearchResult] = []
        for source in loaded.sources:
            await self.build_search_results(source, loaded, built)
        for item in built:
            key = same_scene(item.scene_url)
            if not item.scene_url or key in seen:
                continue
            seen.add(key)
            results.append(item)

    async def paginate_search(
        self,
        *,
        fetch_rows: Callable[[int], Awaitable[list[Any] | None]],
        build_row: Callable[[Any], SearchResult | None],
        max_pages: int,
        full_page: int | None = None,
        stop_on_empty_page: bool = False,
        should_continue: Callable[[list[SearchResult]], bool] | None = None,
        dedup: bool = True,
        dedup_key: Callable[[SearchResult], str] | None = None,
    ) -> list[SearchResult]:
        key = dedup_key or (lambda r: r.scene_url or '')
        seen: set[str] = set()
        out: list[SearchResult] = []
        for page in range(1, max_pages + 1):
            rows = await fetch_rows(page)
            if rows is None:
                break
            built = 0
            for row in rows:
                result = build_row(row)
                if result is None:
                    continue
                built += 1
                if dedup:
                    k = key(result)
                    if not k or k in seen:
                        continue
                    seen.add(k)
                out.append(result)
            if stop_on_empty_page and built == 0:
                break
            if full_page is not None and len(rows) < full_page:
                break
            if should_continue is not None and not should_continue(out):
                break
        return out

    async def fetch_candidate_pages(
        self, urls: list[str], ctx: FetchCtx | None = None, label: Callable[[str], str] | None = None, limit: int = 3
    ) -> list[tuple[str, dict[str, Any] | None]]:
        sem = asyncio.Semaphore(limit)

        async def one(url: str) -> tuple[str, dict[str, Any] | None]:
            async with sem:
                return url, await self.fetch_and_load(url, ctx, label(url) if label else None)

        return list(await asyncio.gather(*(one(url) for url in urls)))

    search_rows_xpath: str | None = None
    candidate_include: tuple[str, ...] | None = None
    candidate_exclude: tuple[str, ...] = ()

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        if self.candidate_include is not None:
            return await self._load_candidate_pages(search_data)
        if not self.search_rows_xpath:
            return None
        url = search_data.search_url()
        found = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search "{search_data.title}"')
        if not found:
            return None
        sources = list(found['sel'].xpath(self.search_rows_xpath))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture, sel=found['sel'])

    async def build_search_results(self, source: Any, loaded: LoadedSearch, results: list[SearchResult]) -> None:
        scene_url = await self.fetch_search_scene_url(source, loaded)
        if not scene_url:
            return
        title = await self.fetch_search_title(source, loaded)
        if not title:
            return
        date = await self.fetch_search_date(source, loaded)
        score = await self.fetch_search_score(source, loaded)
        thumb_url = await self.fetch_search_thumb_url(source, loaded)
        subsite = await self.fetch_search_subsite(source, loaded)
        results.append(
            build_search_result(
                site=loaded.site,
                title=title,
                scene_url=scene_url,
                query=loaded.ctx.title,
                display_date=date,
                search_date=loaded.ctx.search_date,
                score=score,
                thumb_url=thumb_url,
                subsite=subsite,
                cur_id=self.search_cur_id(scene_url, date, loaded),
            )
        )

    def search_cur_id(self, scene_url: str, date: str | None, loaded: LoadedSearch) -> str:
        return pack_cur_id([p for p in (scene_url, date) if p])

    async def candidate_urls(self, search_data: SearchContext) -> list[str]:
        return []

    async def _load_candidate_pages(self, search_data: SearchContext) -> LoadedSearch:
        urls = await self.candidate_urls(search_data)
        include, exclude = list(self.candidate_include or ()) or None, list(self.candidate_exclude) or None
        for url in await web_search_urls(search_data.title, search_data.site_info, include=include, exclude=exclude):
            if url not in urls:
                urls.append(url)

        pages = await self.fetch_candidate_pages(
            list(dict.fromkeys(urls)), FetchCtx(capture=search_data.capture), lambda url: f'[{search_data.site_info.name}] candidate {url}'
        )
        sources = [CandidatePage(url=url, sel=page['sel'], html=page['html']) for url, page in pages if page]
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        if isinstance(source, CandidatePage) and self.title_xpath:
            return self.first_of(source.sel, self.title_xpath)
        return ''

    search_url_xpath: str | None = None

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        if isinstance(source, CandidatePage):
            return source.url
        if not self.search_url_xpath:
            return ''
        href = first_attr(source, self.search_url_xpath)
        if not href:
            return ''

        return absolute_url(href, loaded.site.base_url)

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        return None

    async def fetch_search_score(self, source: Any, loaded: LoadedSearch) -> float | None:
        return None

    async def fetch_search_thumb_url(self, source: Any, loaded: LoadedSearch) -> str | None:
        return None

    async def fetch_search_subsite(self, source: Any, loaded: LoadedSearch) -> str | None:
        return None

    # ── Shared Dedup Helpers ─────────────────────────────────────────────────────

    def dedup_people(self, entries: list[ActorResult]) -> list[ActorResult]:
        out: list[ActorResult] = []
        seen: set[str] = set()
        for e in entries:
            name = (e.name or '').strip()
            if not name or name in seen:
                continue
            seen.add(name)
            out.append(ActorResult(name=name, photo_url=e.photo_url or '', gender=e.gender or '', role=e.role or ''))
        return out

    def dedup_strings(self, values: list[str | None]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for v in values:
            t = (v or '').strip()
            if not t or t in seen:
                continue
            seen.add(t)
            out.append(t)
        return out

    def image_collector(self, clean: Any = None) -> ImageCollector:
        return ImageCollector(clean=clean)

    def group_genre_for(self, cast: int) -> str | None:
        if cast == 3:
            return 'Threesome'
        if cast == 4:
            return 'Foursome'
        if cast > 4:
            return 'Orgy'
        return None

    async def resolve_actor_photos(
        self,
        refs: list[tuple[str, str]],
        extract_photo: Callable[[Selector], str],
        *,
        capture: list[RawCaptureEntry] | None = None,
        label: str = 'actor',
        limit: int = 3,
    ) -> list[ActorResult]:
        seen: set[str] = set()
        unique: list[tuple[str, str]] = []
        for actor_name, href in refs:
            clean = (actor_name or '').strip()
            if clean and clean not in seen:
                seen.add(clean)
                unique.append((clean, href))

        sem = asyncio.Semaphore(limit)

        async def _resolve(name: str, href: str) -> ActorResult:
            photo = ''
            if href:
                async with sem:
                    model_page_elements = await self.fetch_and_load(href, FetchCtx(capture=capture), f'[{label}] {name}')
                if model_page_elements:
                    photo = extract_photo(model_page_elements['sel'])
            return ActorResult(name=name, photo_url=photo)

        return list(await asyncio.gather(*(_resolve(actor_name, href) for actor_name, href in unique)))

    async def enrich_from_data18(
        self,
        metadata: SceneDetail,
        site: ResolvedSiteInfo,
        *,
        scene_id: str | None,
        providers: list[str],
        title: str | None = None,
        scene_date: str | None = None,
        images: list[str] | None = None,
        forced_url: str | None = None,
        kind: Literal['scene', 'movie'] = 'scene',
        allow_square: bool = True,
        search: bool = True,
        actors: list[str] | None = None,
    ) -> None:
        if not (site.scraper_config.data18_enrichment and env.data18_enabled):
            return
        if self._data18_enricher is None:
            if _enricher_factory is None:
                return
            self._data18_enricher = _enricher_factory()
        date = scene_date if scene_date is not None else metadata.release_date
        metadata.data18_url = await self._data18_enricher.enrich_images(
            scope=site.name,
            images=metadata.art if images is None else images,
            priority=metadata.art_priority,
            scene_id=scene_id,
            title=metadata.title if title is None else title,
            providers=providers,
            scene_date=datetime.fromisoformat(date) if date else None,
            forced_url=forced_url,
            kind=kind,
            allow_square=allow_square,
            search=search,
            actors=actors,
        )

    async def fetch_scene_detail(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> SceneDetail | None:
        if self.pacer is None:
            async with FAST_GATE.turn(bool(ctx and ctx.allow_slow)):
                return await self._scene_detail_flow(payload, site, ctx)
        async with self.pacer.scene(bool(ctx and ctx.allow_slow)):
            detail = await self._scene_detail_flow(payload, site, ctx)
            await self.pacer.cooldown('post-update')
            if detail:
                await self.after_scene_scrape(detail)
            return detail

    async def after_scene_scrape(self, detail: SceneDetail) -> None:
        return None

    async def _scene_detail_flow(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> SceneDetail | None:
        scene = await self.load_scene_context(payload, site, ctx)
        if not scene:
            return None

        metadata = SceneDetail(
            scene_url=scene.url,
            art_referer=scene.art_referer,
            art_cookie=scene.art_cookie,
            data18_url=scene.data18_url,
            source_kind=scene.source_kind,
            source_json=scene.source_json,
        )
        await self.update(metadata, scene)

        metadata.title = metadata.title or ''
        metadata.summary = metadata.summary or ''
        metadata.studio = metadata.studio or site.name
        metadata.release_date = metadata.release_date or scene.scene_date or None
        return metadata

    async def update(self, metadata: SceneDetail, scene: LoadedScene) -> None:
        hooks: tuple[tuple[str, Any], ...] = (
            ('title', self.fetch_title),
            ('summary', self.fetch_summary),
            ('studio', self.fetch_studio),
            ('tagline', self.fetch_tagline),
            ('release_date', self.fetch_release_date),
            ('genres', self.fetch_genres),
            ('actors', self.fetch_actors),
            ('directors', self.fetch_directors),
            ('producers', self.fetch_producers),
            ('collections', self.fetch_collections),
            ('image_urls', self.fetch_image_urls),
        )
        gathered = await asyncio.gather(*(fn(scene, metadata) for _, fn in hooks), return_exceptions=True)
        for (name, _), value in zip(hooks, gathered, strict=True):
            if isinstance(value, BaseException):
                if not isinstance(value, Exception):
                    raise value
                logger.warn(scene.site.name, f'fetch_{name} failed for {scene.url}: {value!r}')

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        pipe = payload.find('|')
        url = payload[:pipe] if pipe >= 0 else payload
        fallback_date = payload[pipe + 1 :].strip() if pipe >= 0 else None
        packed: str | None = None
        if self.packed_scene_tail and fallback_date:
            date_part, _, packed = fallback_date.partition('|')
            fallback_date = date_part.strip()
        capture = ctx.capture if ctx else None
        details_page_elements = await self.fetch_and_load(url, FetchCtx(capture=capture), f'GET {url}')
        if not details_page_elements:
            logger.warn(site.name, f'load_scene_context: {url} failed')
            return None
        return LoadedScene(
            url=url,
            site=site,
            scene_date=fallback_date or None,
            capture=capture,
            extra=packed,
            sel=details_page_elements['sel'],
            html=details_page_elements['html'],
            subsite=ctx.subsite if ctx else None,
            language=ctx.language if ctx else None,
        )

    async def load_scene_with_extra_tail(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None, extra_key: str) -> LoadedScene | None:
        pipe = payload.find('|')
        url = payload[:pipe] if pipe >= 0 else payload
        tail = payload[pipe + 1 :].strip() if pipe >= 0 else ''
        details_page_elements = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture if ctx else None), f'[{site.name}] detail {url}')
        if not details_page_elements:
            return None

        return LoadedScene(
            url=url,
            site=site,
            capture=ctx.capture if ctx else None,
            sel=details_page_elements['sel'],
            html=details_page_elements['html'],
            extra={extra_key: tail},
        )

    title_xpath: str | tuple[str, ...] | None = None
    summary_xpath: str | tuple[str, ...] | None = None
    genres_xpath: str | None = None
    actors_xpath: str | None = None

    @staticmethod
    def first_of(sel: Selector, xpaths: str | tuple[str, ...]) -> str:
        for xpath in (xpaths,) if isinstance(xpaths, str) else xpaths:
            found = first_text(sel, xpath)
            if found:
                return found
        return ''

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        if self.title_xpath:
            metadata.title = self.first_of(scene.require_sel(), self.title_xpath)

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        if self.summary_xpath:
            metadata.summary = self.first_of(scene.require_sel(), self.summary_xpath)

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.provider_name or scene.site.name

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        return None

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        return None

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        return None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        if not self.genres_xpath:
            return
        values: list[str | None] = [node.xpath('normalize-space(.)').get() for node in scene.require_sel().xpath(self.genres_xpath)]
        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        if not self.actors_xpath:
            return
        entries = [ActorResult(name=node.xpath('normalize-space(.)').get() or '') for node in scene.require_sel().xpath(self.actors_xpath)]
        metadata.actors = self.dedup_people(entries)

    async def fetch_directors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        return None

    async def fetch_producers(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        return None

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        return None
