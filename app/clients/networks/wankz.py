from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_attr
from app.utils.processors.similarity import compare_string

STUDIO = 'Wankz'


class WankzClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {url}')
        if not loaded:
            return None
        sources: list[Any] = list(loaded['sel'].xpath('//div[contains(@class,"scene")]'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return (source.xpath('(.//div[contains(@class,"title-wrapper")]//a[contains(@class,"title")])[1]').xpath('string(.)').get() or '').strip()

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//a)[1]/@href')
        return absolute_url(href, loaded.site.base_url) if href else ''

    async def fetch_search_score(self, source: Any, loaded: LoadedSearch) -> float | None:
        title = (source.xpath('(.//div[contains(@class,"title-wrapper")]//a[contains(@class,"title")])[1]').xpath('string(.)').get() or '').strip()
        sub_site = (source.xpath('(.//div[contains(@class,"series-container")]//a[contains(@class,"sitename")])[1]').xpath('string(.)').get() or '').strip()
        site_dist = compare_string(sub_site.lower(), loaded.site.name.lower()).levenshtein
        title_dist = compare_string(loaded.ctx.title.lower(), title.lower()).levenshtein
        return 80 - (site_dist * 8) // 10 + (20 - (title_dist * 2) // 10)

    async def fetch_search_subsite(self, source: Any, loaded: LoadedSearch) -> str | None:
        return (source.xpath('(.//div[contains(@class,"series-container")]//a[contains(@class,"sitename")])[1]').xpath('string(.)').get() or '').strip() or None

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//div[contains(@class,"title")]//h1)[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//div[contains(@class,"description")]//p)[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [STUDIO]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//div[contains(@class,"views")]//span)[1]').xpath('string(.)').get() or '').replace('Added', '').strip()
        if raw:
            return iso_date(raw)
        return (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [el.xpath('normalize-space(.)').get() for el in scene.sel.xpath('//a[contains(@class,"cat")] | //p[@style]//a')]
        return self.dedup_strings(values) or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        entries = [
            ActorResult(
                name=(el.xpath('(.//span)[1]').xpath('string(.)').get() or '').strip(),
                photo_url=first_attr(el, '(.//img)[1]/@src'),
            )
            for el in scene.sel.xpath('//div[contains(@class,"actors")]//a[contains(@class,"model")]')
        ]
        return self.dedup_people(entries) or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        coll = self.image_collector(lambda raw: absolute_url(raw, scene.site.base_url))
        for raw in scene.sel.xpath('//a[contains(@class,"noplayer")]//img/@src').getall():
            coll['push'](raw)
        images: list[str] = coll['list']
        return images or None
