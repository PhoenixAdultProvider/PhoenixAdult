from __future__ import annotations

import asyncio
import json
from abc import ABC
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, cast

import httpx2
from parsel import Selector

from app.config.env import env
from app.utils.helpers.helpers import b64url_decode, b64url_encode, build_search_result, pack_cur_id
from app.utils.http.bypass import bypass_get
from app.utils.http.client import make_http
from app.utils.logging.logger import logger

if TYPE_CHECKING:
    from app.registry import ResolvedSiteInfo


# ── Capture (raw-response debugging, surfaced by the dev UI) ──────────────────


@dataclass
class RawCaptureEntry:
    label: str
    content_type: Literal['json', 'html']
    body: Any


# ── Phase contexts ────────────────────────────────────────────────────────────


@dataclass
class SearchContext:
    title: str
    encoded: str
    search_site: str
    site_info: ResolvedSiteInfo
    search_date: str | None = None
    year: int | None = None
    duration: str | None = None
    ohash: str | None = None
    capture: list[RawCaptureEntry] | None = None
    language: str | None = None
    scene_id: str | None = None
    full_title: str | None = None


@dataclass
class SceneContext:
    capture: list[RawCaptureEntry] | None = None
    language: str | None = None


# ── Results ───────────────────────────────────────────────────────────────────


@dataclass
class SearchResult:
    title: str
    scene_url: str
    cur_id: str
    thumb_url: str | None = None
    release_date: str | None = None
    display_date: str | None = None
    score: float | None = None
    search_url: str | None = None


@dataclass
class ActorResult:
    name: str
    photo_url: str = ''
    gender: str = ''


@dataclass
class SceneDetail:
    title: str
    summary: str
    studio: str
    genres: list[str]
    actors: list[ActorResult]
    raw_image_urls: list[str]
    raw_image_referer: str | None = None
    raw_image_cookie: str | None = None
    tagline: str | None = None
    release_date: str | None = None
    year: int | None = None
    collections: list[str] | None = None
    directors: list[ActorResult] | None = None
    producers: list[ActorResult] | None = None
    scene_url: str | None = None


# ── Loaded contexts handed to the per-field hooks ─────────────────────────────


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
    raw_image_referer: str | None = None
    raw_image_cookie: str | None = None


@dataclass
class LoadedSearch:
    ctx: SearchContext
    site: ResolvedSiteInfo
    sources: list[Any]
    capture: list[RawCaptureEntry] | None = None
    sel: Selector | None = None
    extra: Any = None


@dataclass
class FetchCtx:
    capture: list[RawCaptureEntry] | None = None
    use_bypass: bool = False
    headers: dict[str, str] | None = None


def _bypass_enabled(ctx: FetchCtx | None) -> bool:
    if ctx and ctx.use_bypass:
        return True
    return env.bypass_auto_retry


# ── Base Client ───────────────────────────────────────────────────────────────


class Client(ABC):  # noqa: B024 - abstract by intent; subclasses override hooks, none are mandatory
    def __init__(self, extra_headers: dict[str, str] | None = None) -> None:
        self._extra_headers = extra_headers or {}
        self._http: httpx2.AsyncClient | None = None

    @property
    def http(self) -> httpx2.AsyncClient:
        if self._http is None:
            self._http = make_http(self._extra_headers)
        return self._http

    def encode(self, s: str) -> str:
        return b64url_encode(s)

    def decode(self, s: str) -> str:
        return b64url_decode(s)

    def tag(self, site: ResolvedSiteInfo) -> str:
        return site.name

    # ── Fetch helpers ──────────────────────────────────────────────────────────

    async def fetch_and_load(self, url: str, ctx: FetchCtx | None = None, label: str | None = None) -> dict[str, Any] | None:
        direct = await self._direct_get(url, ctx.headers if ctx else None)
        if direct and direct['ok']:
            if ctx and ctx.capture is not None:
                ctx.capture.append(RawCaptureEntry(label or f'GET {url}', 'html', direct['body']))
            return {'status': direct['status'], 'html': direct['body'], 'sel': Selector(text=direct['body'])}
        if not _bypass_enabled(ctx):
            if direct:
                logger.debug(f'fetch_and_load {url} → HTTP {direct["status"]}')
            return None
        bypass = await bypass_get(url, (ctx.headers if ctx else None) or {})
        if not bypass or bypass.status >= 400:
            logger.debug(f'fetch_and_load {url} → bypass also failed (status={bypass.status if bypass else "none"})')
            return None
        logger.info(f'fetch_and_load {url} → recovered via bypass ({bypass.status})')
        if ctx and ctx.capture is not None:
            ctx.capture.append(RawCaptureEntry(f'{label} (bypass)' if label else f'GET {url} (bypass)', 'html', bypass.body))
        return {'status': bypass.status, 'html': bypass.body, 'sel': Selector(text=bypass.body)}

    async def fetch_json(self, url: str, ctx: FetchCtx | None = None, headers: dict[str, str] | None = None, label: str | None = None) -> Any | None:
        try:
            r = await self.http.get(url, headers=headers)
            if r.status_code < 400:
                data = r.json()
                if ctx and ctx.capture is not None:
                    ctx.capture.append(RawCaptureEntry(label or f'GET {url}', 'json', data))
                return data
            logger.debug(f'fetch_json {url} → HTTP {r.status_code}')
        except (httpx2.HTTPError, ValueError) as err:
            logger.debug(f'fetch_json {url} threw: {err}')
        if not _bypass_enabled(ctx):
            return None
        bypass = await bypass_get(url, headers or {})
        if not bypass or bypass.status >= 400:
            logger.debug(f'fetch_json {url} → bypass also failed (status={bypass.status if bypass else "none"})')
            return None
        try:
            parsed = json.loads(bypass.body)
        except ValueError as err:
            logger.debug(f"fetch_json {url} → bypass body wasn't JSON: {err}")
            return None
        logger.info(f'fetch_json {url} → recovered via bypass ({bypass.status})')
        if ctx and ctx.capture is not None:
            ctx.capture.append(RawCaptureEntry(f'{label} (bypass)' if label else f'GET {url} (bypass)', 'json', parsed))
        return parsed

    async def _direct_get(self, url: str, headers: dict[str, str] | None = None) -> dict[str, Any] | None:
        try:
            r = await self.http.get(url, headers=headers)
            # A 202 or empty-body response is an anti-bot soft-block, not a usable
            # page — mark it not-ok so the bypass fallback can fire.
            ok = r.status_code < 400 and r.status_code != 202 and bool(r.text.strip())
            return {'ok': ok, 'status': r.status_code, 'body': r.text}
        except httpx2.HTTPError:
            return None

    # ── Search orchestrator ─────────────────────────────────────────────────────

    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        loaded = await self.load_search_context(ctx)
        if not loaded:
            return []
        seen: set[str] = set()
        out: list[SearchResult] = []
        for source in loaded.sources:
            for item in await self.build_search_results(source, loaded):
                if not item.scene_url or item.scene_url in seen:
                    continue
                seen.add(item.scene_url)
                out.append(item)
        return out

    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        return None

    async def build_search_results(self, source: Any, loaded: LoadedSearch) -> list[SearchResult]:
        scene_url = await self.fetch_search_scene_url(source, loaded)
        if not scene_url:
            return []
        title = await self.fetch_search_title(source, loaded)
        if not title:
            return []
        date = await self.fetch_search_date(source, loaded)
        score = await self.fetch_search_score(source, loaded)
        thumb_url = await self.fetch_search_thumb_url(source, loaded)
        return [
            build_search_result(
                title=title,
                scene_url=scene_url,
                query=loaded.ctx.title,
                display_date=date,
                search_date=loaded.ctx.search_date,
                score=score,
                thumb_url=thumb_url,
                cur_id=pack_cur_id([p for p in (scene_url, date) if p]),
            )
        ]

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return ''

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        return ''

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        return None

    async def fetch_search_score(self, source: Any, loaded: LoadedSearch) -> float | None:
        return None

    async def fetch_search_thumb_url(self, source: Any, loaded: LoadedSearch) -> str | None:
        return None

    # ── Shared dedup helpers ─────────────────────────────────────────────────────

    def dedup_people(self, entries: list[ActorResult]) -> list[ActorResult]:
        out: list[ActorResult] = []
        seen: set[str] = set()
        for e in entries:
            name = (e.name or '').strip()
            if not name or name in seen:
                continue
            seen.add(name)
            out.append(ActorResult(name=name, photo_url=e.photo_url or '', gender=e.gender or ''))
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

    def image_collector(self, clean: Any = None) -> dict[str, Any]:
        out: list[str] = []

        def push(raw: str | None) -> None:
            if not raw:
                return
            url = clean(raw) if clean else raw
            if url and url not in out:
                out.append(url)

        return {'push': push, 'list': out}

    # ── Detail orchestrator ──────────────────────────────────────────────────────

    async def fetch_scene_detail(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> SceneDetail | None:
        scene = await self.load_scene_context(payload, site, ctx)
        if not scene:
            return None

        # asyncio.gather collapses >6 awaitables to list[union] for type checkers;
        # cast back to the precise per-field tuple the hooks actually return.
        gathered = cast(
            tuple[
                str | None,
                str | None,
                str | None,
                str | None,
                str | None,
                list[str] | None,
                list[ActorResult] | None,
                list[ActorResult] | None,
                list[ActorResult] | None,
                list[str] | None,
                list[str] | None,
            ],
            await asyncio.gather(
                self.fetch_title(scene),
                self.fetch_summary(scene),
                self.fetch_studio(scene),
                self.fetch_tagline(scene),
                self.fetch_release_date(scene),
                self.fetch_genres(scene),
                self.fetch_actors(scene),
                self.fetch_directors(scene),
                self.fetch_producers(scene),
                self.fetch_collections(scene),
                self.fetch_image_urls(scene),
            ),
        )
        (title, summary, studio, tagline, release_date, genres, actors, directors, producers, collections, raw_image_urls) = gathered

        return SceneDetail(
            title=title or '',
            summary=summary or '',
            studio=studio or site.name,
            tagline=tagline,
            release_date=release_date or scene.scene_date or None,
            genres=genres or [],
            actors=actors or [],
            directors=directors,
            producers=producers,
            collections=collections,
            raw_image_urls=raw_image_urls or [],
            raw_image_referer=scene.raw_image_referer,
            raw_image_cookie=scene.raw_image_cookie,
            scene_url=scene.url,
        )

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        pipe = payload.find('|')
        url = payload[:pipe] if pipe >= 0 else payload
        fallback_date = payload[pipe + 1 :].strip() if pipe >= 0 else None
        try:
            r = await self.http.get(url)
        except httpx2.HTTPError as err:
            logger.warn(site.name, f'load_scene_context: {url} failed — {err}')
            return None
        if ctx and ctx.capture is not None:
            ctx.capture.append(RawCaptureEntry(f'GET {url}', 'html', r.text))
        return LoadedScene(
            url=url,
            site=site,
            scene_date=fallback_date or None,
            capture=ctx.capture if ctx else None,
            sel=Selector(text=r.text),
            html=r.text,
        )

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        return None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        return None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return None

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return None

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        return None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        return None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        return None

    async def fetch_directors(self, scene: LoadedScene) -> list[ActorResult] | None:
        return None

    async def fetch_producers(self, scene: LoadedScene) -> list[ActorResult] | None:
        return None

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        return None

    def image_rule(self, site: ResolvedSiteInfo) -> Literal['aspect', 'threshold']:
        return 'threshold'
