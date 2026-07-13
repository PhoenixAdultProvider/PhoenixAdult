from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_attr, first_text


class VirtualTabooClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//a[contains(@class,"video-card__item")]'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/div[contains(@class,"video-card__title")]')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '@href')
        if not href:
            return ''
        return absolute_url(href, loaded.site.base_url)

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        metadata.title = first_text(sel, '//div[contains(@class,"right-info")]//h1') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        full = first_text(sel, '//div[contains(@class,"description")]//span[contains(@class,"full")]')
        if full:
            metadata.summary = full
            return
        metadata.summary = first_text(sel, '//details[contains(@class,"description")]') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name or ''

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        raw = first_text(sel, '//div[contains(@class,"info mt-5")]')
        parts = raw.split('•')
        if len(parts) < 2:
            if scene.scene_date:
                metadata.release_date = iso_date(scene.scene_date) or scene.scene_date
            return
        date_raw = parts[1].strip()
        metadata.release_date = iso_date(date_raw) if date_raw else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        values: list[str | None] = [el.xpath('normalize-space(.)').get() for el in sel.xpath('//div[contains(@class,"tag-list")]')]
        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        entries = [
            ActorResult(name=(a.xpath('normalize-space(.)').get() or ''))
            for a in sel.xpath('//div[contains(@class,"right-info")]//div[contains(@class,"info")]//a')
        ]
        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        base = scene.site.base_url
        coll = self.image_collector(lambda raw: absolute_url((raw or '').strip().split('?')[0], base))
        coll['push'](sel.xpath('(//meta[@property="og:image"]/@content)[1]').get() or '')
        for href in sel.xpath('//div[contains(@class,"gallery-item")]//a/@href').getall():
            coll['push'](href)
        metadata.art = coll['list']
