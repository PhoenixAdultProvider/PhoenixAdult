from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date

STUDIO = 'Perfect Gonzo'
_SUMMARY_DIV = 'col-sm-8 col-md-8 no-padding-side'
_TAGS_DIV = 'col-sm-8 col-md-8 no-padding-side tag-container'
_ACTOR_DIV = 'col-sm-3 col-md-3 col-md-offset-1 no-padding-side'
_DATE_DIV = 'col-sm-6 col-md-6 no-padding-left no-padding-right text-right'


class PerfectGonzoClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {url}')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//div[@class="itemm"]'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return (source.xpath('(.//a)[1]/@title').get() or '').strip()

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = (source.xpath('(.//a)[1]/@href').get() or '').strip()
        return absolute_url(href, loaded.site.base_url) if href else ''

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw = (source.xpath('(.//span[@class="nm-date"])[1]').xpath('string(.)').get() or '').strip()
        return (iso_date(raw) if raw else None) or loaded.ctx.search_date

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//h2)[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath(f'(//div[@class="{_SUMMARY_DIV}"]/p)[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = (scene.sel.xpath(f'(//div[@class="{_DATE_DIV}"]/span)[1]').xpath('string(.)').get() or '').strip()
        if raw:
            after = raw.split('Added')[-1].strip()
            if after:
                return iso_date(after)
        return (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        genres: list[str] = []
        for a in scene.sel.xpath(f'//div[@class="{_TAGS_DIV}"]//a'):
            g = (a.xpath('normalize-space(.)').get() or '').strip().lower()
            if g and g not in genres:
                genres.append(g)
        return genres or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in scene.sel.xpath(f'//div[@class="{_ACTOR_DIV}"]/p/a'):
            name = (el.xpath('normalize-space(.)').get() or '').strip()
            href = (el.xpath('@href').get() or '').strip()
            if not name or not href or name in seen:
                continue
            seen.add(name)
            page = await self.fetch_and_load(absolute_url(href, base), None, f'[{scene.site.name}] actor {name}')
            raw = (page['sel'].xpath('(//div[@class="col-md-8 bigmodelpic"]/img)[1]/@src').get() or '').strip() if page else ''
            photo = (absolute_url(raw, base)) if raw else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        coll = self.image_collector(lambda raw: absolute_url(raw, scene.site.base_url))
        for poster in scene.sel.xpath('//video/@poster').getall():
            coll['push'](poster)
        for img in scene.sel.xpath('//ul[@class="bxslider_screenshots"]//img'):
            coll['push'](img.xpath('@src').get() or img.xpath('@data-original').get())
        images: list[str] = coll['list']
        return images or None
