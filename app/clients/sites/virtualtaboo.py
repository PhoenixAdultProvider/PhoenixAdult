from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_text


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
        href = (source.xpath('@href').get() or '').strip()
        if not href:
            return ''
        return href if href.startswith('http') else absolute_url(href, loaded.site.base_url)

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//div[contains(@class,"right-info")]//h1') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        full = first_text(scene.sel, '//div[contains(@class,"description")]//span[contains(@class,"full")]')
        if full:
            return full
        return first_text(scene.sel, '//details[contains(@class,"description")]') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//div[contains(@class,"info mt-5")]')
        parts = raw.split('•')
        if len(parts) < 2:
            if scene.scene_date:
                return iso_date(scene.scene_date) or scene.scene_date
            return None
        date_raw = parts[1].strip()
        return iso_date(date_raw) if date_raw else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [el.xpath('normalize-space(.)').get() for el in scene.sel.xpath('//div[contains(@class,"tag-list")]')]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        entries = [
            ActorResult(name=(a.xpath('normalize-space(.)').get() or ''))
            for a in scene.sel.xpath('//div[contains(@class,"right-info")]//div[contains(@class,"info")]//a')
        ]
        return self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        images: list[str] = []

        def push(raw: str) -> None:
            url = (raw or '').strip().split('?')[0]
            if not url:
                return
            abs_url = url if url.startswith('http') else absolute_url(url, base)
            if abs_url not in images:
                images.append(abs_url)

        push(scene.sel.xpath('(//meta[@property="og:image"]/@content)[1]').get() or '')
        for href in scene.sel.xpath('//div[contains(@class,"gallery-item")]//a/@href').getall():
            push(href)
        return images
