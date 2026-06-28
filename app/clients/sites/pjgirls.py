from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_text


class PJGirlsClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//div[contains(@class,"thumb") and contains(@class,"video")]'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/h2')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = (source.xpath('(.//a/@href)[1]').get() or '').strip()
        if not href:
            return ''
        return absolute_url(href, loaded.site.base_url)

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        return iso_date(first_text(source, '(.//a//div//span)[2]'))

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//title').split('- porn video')[0].strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//div[contains(@class,"text")]/p') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return 'PJGirls'

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '(//div[contains(@class,"info")]/h3)[1]')
        return (iso_date(raw, '%B %d, %Y') if raw else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [
            a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//div[contains(@class,"detailTagy") and contains(@class,"clear")]//a')
        ]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        for el in scene.sel.xpath('(//div[contains(@class,"info")]/h3)[3]//a'):
            name = (el.xpath('normalize-space(.)').get() or '').strip()
            if not name:
                continue
            photo = ''
            href = (el.xpath('@href').get() or '').strip()
            if href:
                loaded = await self.fetch_and_load(absolute_url(href, scene.site.base_url), FetchCtx(capture=scene.capture), f'GET {href} (actor)')
                raw = (loaded['sel'].xpath('(//div[contains(@class,"image")]//img/@src)[1]').get() or '').strip() if loaded else ''
                photo = (absolute_url(raw, scene.site.base_url)) if raw else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        images: list[str] = []
        for raw in scene.sel.xpath('//div[contains(@class,"videoObal")]//img/@src').getall():
            raw = (raw or '').strip()
            if not raw:
                continue
            abs_url = absolute_url(raw, scene.site.base_url)
            if abs_url not in images:
                images.append(abs_url)
        return images
