from __future__ import annotations

import asyncio
import json
from abc import ABC
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

import httpx2
from parsel import Selector

from app.config.env import env
from app.utils.helpers.helpers import b64url_decode, b64url_encode, build_search_result, pack_cur_id
from app.utils.http.bypass import bypass_get
from app.utils.http.client import make_http
from app.utils.images.logo_cache import resolve_logo
from app.utils.logging.logger import logger

if TYPE_CHECKING:
    from app.clients.aggregators.data18 import Data18Client
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
    subsite: str | None = None  # sub-site the search selection resolved to; used for data18 slugging
    allow_slow: bool = False  # background scrape: pacing may sleep past the Plex request budget


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
    subsite: str | None = None


@dataclass
class ActorResult:
    name: str
    photo_url: str = ''
    gender: str = ''
    role: str = ''


class PacingDeferredError(Exception):
    """A client refused to hold a Plex-facing request through a long pacing wait (Plex
    kills provider requests at ~90s); the service queues a background scrape instead."""

    def __init__(self, wait_seconds: float) -> None:
        super().__init__(f'pacing requires waiting ~{wait_seconds:.0f}s')
        self.wait_seconds = wait_seconds


@dataclass
class SceneDetail:
    title: str = ''
    summary: str = ''
    studio: str = ''
    genres: list[str] = field(default_factory=list)
    actors: list[ActorResult] = field(default_factory=list)
    art: list[str] = field(default_factory=list)
    art_referer: str | None = None
    art_cookie: str | None = None
    tagline: str | None = None
    release_date: str | None = None
    year: int | None = None
    collections: list[str] | None = None
    directors: list[ActorResult] | None = None
    producers: list[ActorResult] | None = None
    scene_url: str | None = None
    original_title: str | None = None
    data18_url: str | None = None
    duration: int | None = None  # milliseconds
    countries: list[str] | None = None
    rating: float | None = None
    audience_rating: float | None = None
    logo: str | None = None


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
    art_referer: str | None = None
    art_cookie: str | None = None
    data18_url: str | None = None
    subsite: str | None = None
    language: str | None = None

    def require_sel(self) -> Selector:
        if self.sel is None:
            raise ValueError(f'{self.url}: scene has no parsed HTML')
        return self.sel


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
        self._data18_enricher: Data18Client | None = None

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
            direct_status = direct['status'] if direct else 'error'
            logger.warn(f'fetch_and_load {url} failed — direct HTTP {direct_status}, bypass status={bypass.status if bypass else "none"}')
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
            logger.warn(f'fetch_json {url} failed — direct and bypass exhausted (bypass status={bypass.status if bypass else "none"})')
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

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        """Append SearchResults for `ctx` to `results`. The default drives the search-context
        loader + per-row builder and de-duplicates by scene_url; wholesale clients override
        this and append directly. The caller owns the list and reads it back."""
        loaded = await self.load_search_context(search_data)
        if not loaded:
            return
        seen = {r.scene_url for r in results if r.scene_url}
        built: list[SearchResult] = []
        for source in loaded.sources:
            await self.build_search_results(source, loaded, built)
        for item in built:
            if not item.scene_url or item.scene_url in seen:
                continue
            seen.add(item.scene_url)
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
        """Drive a paged search: fetch each page's rows, map + dedup them, and stop on
        a short/empty page, the page cap, fetch_rows returning None, or should_continue."""
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

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        return None

    async def build_search_results(self, source: Any, loaded: LoadedSearch, results: list[SearchResult]) -> None:
        """Build one SearchResult from `source` via the fetch_search_* hooks and append it
        to `results`. Clients with a bespoke row shape override this and append their own."""
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
                title=title,
                scene_url=scene_url,
                query=loaded.ctx.title,
                display_date=date,
                search_date=loaded.ctx.search_date,
                score=score,
                thumb_url=thumb_url,
                subsite=subsite,
                cur_id=pack_cur_id([p for p in (scene_url, date) if p]),
            )
        )

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

    async def fetch_search_subsite(self, source: Any, loaded: LoadedSearch) -> str | None:
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

    def group_genre_for(self, cast: int) -> str | None:
        """The group-sex genre implied by the cast size: 3 → Threesome, 4 → Foursome, 5+ → Orgy.
        Clients on an offset scale (e.g. a POV performer excluded from the count) adjust `cast`."""
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
        """Turn (name, profile_url) refs into ActorResults, fetching the profile pages concurrently
        (at most `limit` in flight) and running `extract_photo` on each loaded page's selector for the
        headshot. De-duplicated by name (first wins), input order preserved. A ref with no URL — or a
        page that fails to load — yields an ActorResult with an empty photo, never an error."""
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
    ) -> None:
        """Resolve the scene's data18 page and merge its images into `images` (default
        metadata.art), recording metadata.data18_url. No-op unless the site opts into
        data18 enrichment and it's enabled; one shared Data18Client per client. `title`
        and `scene_date` default to metadata's own; `scene_date` is an ISO date string."""
        if not (site.scraper_config.data18_enrichment and env.data18_enabled):
            return
        from app.clients.aggregators.data18 import Data18Client

        self._data18_enricher = self._data18_enricher or Data18Client()
        date = scene_date if scene_date is not None else metadata.release_date
        metadata.data18_url = await self._data18_enricher.enrich_images(
            scope=site.name,
            images=metadata.art if images is None else images,
            scene_id=scene_id,
            title=metadata.title if title is None else title,
            providers=providers,
            scene_date=datetime.fromisoformat(date) if date else None,
            forced_url=forced_url,
            kind=kind,
            allow_square=allow_square,
        )

    # ── Detail orchestrator ──────────────────────────────────────────────────────

    async def fetch_scene_detail(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> SceneDetail | None:
        """Public detail entry: load the scene, hand a fresh `metadata` to `update`, then
        apply the studio/date fallbacks and normalize the required fields."""
        scene = await self.load_scene_context(payload, site, ctx)
        if not scene:
            return None

        metadata = SceneDetail(
            scene_url=scene.url,
            art_referer=scene.art_referer,
            art_cookie=scene.art_cookie,
            data18_url=scene.data18_url,
        )
        await self.update(metadata, scene)

        metadata.title = metadata.title or ''
        metadata.summary = metadata.summary or ''
        metadata.studio = metadata.studio or site.name
        metadata.release_date = metadata.release_date or scene.scene_date or None
        metadata.genres = metadata.genres or []
        metadata.actors = metadata.actors or []
        metadata.art = metadata.art or []
        try:
            await self.fetch_logo(scene, metadata)
            metadata.logo = await resolve_logo(metadata.tagline, metadata.studio, metadata.logo)
        except Exception as err:  # noqa: BLE001 - a missing logo never fails the scene
            logger.warn(site.name, f'fetch_logo failed for {scene.url}: {err!r}')
        return metadata

    async def update(self, metadata: SceneDetail, scene: LoadedScene) -> None:
        """Populate `metadata` from the loaded scene. Default runs the field hooks — each
        mutates `metadata` in place — concurrently with per-hook error isolation; wholesale
        clients override this and set metadata.* directly."""
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
        capture = ctx.capture if ctx else None
        details_page_elements = await self.fetch_and_load(url, FetchCtx(capture=capture, use_bypass=site.use_bypass), f'GET {url}')
        if not details_page_elements:
            logger.warn(site.name, f'load_scene_context: {url} failed')
            return None
        return LoadedScene(
            url=url,
            site=site,
            scene_date=fallback_date or None,
            capture=capture,
            sel=details_page_elements['sel'],
            html=details_page_elements['html'],
            subsite=ctx.subsite if ctx else None,
            language=ctx.language if ctx else None,
        )

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        return None

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        return None

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        return None

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        return None

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        return None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        return None

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        return None

    async def fetch_directors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        return None

    async def fetch_producers(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        return None

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        return None

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        return None

    async def fetch_logo(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        """Sets metadata.logo (a clearLogo image URL). Unlike the other hooks this runs
        AFTER update() and the studio fallback, so metadata.tagline / metadata.studio are
        final — logo resolution keys off them (tagline first, then studio)."""
        return None
