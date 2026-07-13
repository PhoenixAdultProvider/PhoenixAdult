from __future__ import annotations

import asyncio
import re
from typing import Any, TypedDict

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.concurrency.coalescer import coalesce_future
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr
from app.utils.processors.title_case import title_case

STUDIO = 'FAKings'
_WS_RE = re.compile(r'\s+')
_DATE_P_XP = '(.//p[contains(@class,"txtmininfo") and contains(@class,"calen") and contains(@class,"sinlimite")])[1]'


class _SceneExtra(TypedDict):
    model_cache: dict[str, asyncio.Future[dict[str, Any] | None]]


class FAKingsClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        encoded = _WS_RE.sub('-', ctx.title.strip())
        en_path = ctx.site_info.search_path.replace('{query}', encoded)
        es_path = en_path.replace('/en/', '/')
        search_urls = [base + en_path, base + es_path]

        seen: set[str] = set()
        for search_url in search_urls:
            loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {search_url}')
            if not loaded:
                continue
            for row in loaded['sel'].xpath('//div[@class="zona-listado2"]'):
                href = first_attr(row, '(.//*[@href])[1]/@href')
                if not href:
                    continue
                scene_url = absolute_url(href, ctx.site_info.base_url)
                if scene_url in seen:
                    continue
                seen.add(scene_url)
                title = (row.xpath('(.//h3)[1]').xpath('string(.)').get() or '').strip()
                if not title:
                    continue
                date_raw = (row.xpath(_DATE_P_XP).xpath('string(.)').get() or '').strip()
                date_iso = iso_date(date_raw) if date_raw else None
                carried = date_iso or ctx.search_date or ''
                results.append(
                    build_search_result(
                        title=title,
                        scene_url=scene_url,
                        query=ctx.title,
                        display_date=date_iso,
                        search_date=ctx.search_date,
                        cur_id=pack_cur_id([x for x in (scene_url, carried) if x]),
                    )
                )

    # ── Detail ──────────────────────────────────────────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        scene = await super().load_scene_context(payload, site, ctx)
        if scene:
            extra: _SceneExtra = {'model_cache': {}}
            scene.extra = extra
        return scene

    def _load_model(self, scene: LoadedScene, url: str) -> asyncio.Future[dict[str, Any] | None]:
        extra: _SceneExtra = scene.extra
        cache = extra['model_cache']
        return coalesce_future(cache, url, lambda: self.fetch_and_load(url, None, f'GET {url} (model)'))

    def _actor_refs(self, scene: LoadedScene) -> list[tuple[str, str]]:
        assert scene.sel is not None
        refs: list[tuple[str, str]] = []
        for a in scene.sel.xpath('(//strong[contains(.,"Actr")])[1]/following-sibling::a'):
            name = first_attr(a, 'normalize-space(.)')
            href = first_attr(a, '@href')
            if name and href:
                refs.append((name, absolute_url(href, scene.site.base_url)))
        return refs

    def _tagline(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//strong[contains(.,"Serie")])[1]/following-sibling::a[1]').xpath('string(.)').get() or '').strip()
        return title_case(raw, site_name=scene.site.name) if raw else None

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = (scene.sel.xpath('(//h1)[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = (scene.sel.xpath('(//span[@class="grisoscuro"])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline(scene)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        tagline = self._tagline(scene)
        metadata.collections = [tagline] if tagline else None

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        genres = [g for g in (first_attr(a, 'normalize-space(.)') for a in scene.sel.xpath('(//strong[contains(.,"Categori")])[1]/following-sibling::a')) if g]
        metadata.genres = genres or []

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        base = scene.site.base_url
        actors: list[ActorResult] = []
        for name, href in self._actor_refs(scene):
            page = await self._load_model(scene, href)
            raw = first_attr(page['sel'], '(//div[@class="zona-imagen"]//img[@class])[1]/@src') if page else ''
            actors.append(ActorResult(name=name, photo_url=absolute_url(raw, base) if raw else ''))
        metadata.actors = actors or []

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        base = scene.site.base_url
        for _name, href in self._actor_refs(scene):
            page = await self._load_model(scene, href)
            if not page:
                continue
            for row in page['sel'].xpath('//div[@class="zona-listado2"]'):
                row_href = first_attr(row, '(.//*[@href])[1]/@href')
                if row_href and absolute_url(row_href, base) == scene.url:
                    poster = first_attr(row, '(.//img[@class])[1]/@src')
                    if poster:
                        metadata.art = [absolute_url(poster, base)]
                        return
