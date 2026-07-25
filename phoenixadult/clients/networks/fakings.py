from __future__ import annotations

import asyncio
import re
from typing import Any, TypedDict

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.concurrency.coalescer import coalesce_future
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from phoenixadult.utils.helpers.html_helpers import first_attr
from phoenixadult.utils.processors.title_case import title_case

STUDIO = 'FAKings'
_WS_RE = re.compile(r'\s+')
_DATE_P_XP = '(.//p[contains(@class,"txtmininfo") and contains(@class,"calen") and contains(@class,"sinlimite")])[1]'


class _SceneExtra(TypedDict):
    model_cache: dict[str, asyncio.Future[dict[str, Any] | None]]


class FAKingsClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        encoded = _WS_RE.sub('-', search_data.title.strip())
        en_path = search_data.site_info.search_path.replace('{query}', encoded)
        es_path = en_path.replace('/en/', '/')
        search_urls = [base + en_path, base + es_path]

        seen: set[str] = set()
        for search_url in search_urls:
            search_results = await self.fetch_and_load(search_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {search_url}')
            if not search_results:
                continue

            for search_result in search_results['sel'].xpath('//div[@class="zona-listado2"]'):
                href = first_attr(search_result, '(.//*[@href])[1]/@href')
                if not href:
                    continue

                scene_url = absolute_url(href, search_data.site_info.base_url)
                if scene_url in seen:
                    continue

                seen.add(scene_url)
                title = (search_result.xpath('(.//h3)[1]').xpath('string(.)').get() or '').strip()
                if not title:
                    continue

                date_raw = (search_result.xpath(_DATE_P_XP).xpath('string(.)').get() or '').strip()
                date_iso = iso_date(date_raw) if date_raw else None
                carried = date_iso or search_data.search_date or ''

                results.append(
                    build_search_result(
                        site=search_data.site_info,
                        title=title,
                        scene_url=scene_url,
                        query=search_data.title,
                        display_date=date_iso,
                        search_date=search_data.search_date,
                        cur_id=pack_cur_id([x for x in (scene_url, carried) if x]),
                    )
                )

    # ── Context Loader ──────────────────────────────────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        scene = await super().load_scene_context(payload, site, ctx)
        if scene:
            extra: _SceneExtra = {'model_cache': {}}
            scene.extra = extra

        return scene

    # ── Update Field Hook Helpers ───────────────────────────────────────────────

    def _load_model(self, scene: LoadedScene, url: str) -> asyncio.Future[dict[str, Any] | None]:
        extra: _SceneExtra = scene.extra
        cache = extra['model_cache']
        return coalesce_future(cache, url, lambda: self.fetch_and_load(url, None, f'GET {url} (model)'))

    def _actor_refs(self, scene: LoadedScene) -> list[tuple[str, str]]:
        details_page_elements = scene.require_sel()

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath('(//strong[contains(.,"Actr")])[1]/following-sibling::a'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name and href:
                refs.append((actor_name, absolute_url(href, scene.site.base_url)))

        return refs

    def _tagline(self, scene: LoadedScene) -> str | None:
        details_page_elements = scene.require_sel()

        raw = (details_page_elements.xpath('(//strong[contains(.,"Serie")])[1]/following-sibling::a[1]').xpath('string(.)').get() or '').strip()
        return title_case(raw, site_name=scene.site.name) if raw else None

    # ── Update Field Hooks ──────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = (details_page_elements.xpath('(//h1)[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = (details_page_elements.xpath('(//span[@class="grisoscuro"])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline(scene) or ''

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        tagline = self._tagline(scene)

        metadata.collections = [tagline] if tagline else None

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres = [
            genre_name
            for genre_name in (
                first_attr(genre_link, 'normalize-space(.)')
                for genre_link in details_page_elements.xpath('(//strong[contains(.,"Categori")])[1]/following-sibling::a')
            )
            if genre_name
        ]

        metadata.genres = genres or []

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        base = scene.site.base_url
        actors: list[ActorResult] = []
        for actor_name, href in self._actor_refs(scene):
            page = await self._load_model(scene, href)
            raw = first_attr(page['sel'], '(//div[@class="zona-imagen"]//img[@class])[1]/@src') if page else ''
            actors.append(ActorResult(name=actor_name, photo_url=absolute_url(raw, base) if raw else ''))

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
