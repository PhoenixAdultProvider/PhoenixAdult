from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date

STUDIO = 'Porndoe Premium'
_TITLE_SEL = './/div[@class="-g-vc-item-title"]//a'


class PorndoePremiumClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {url}')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//div[contains(@class,"main-content")]//div[@class="-g-vc-grid"]'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return (source.xpath(f'({_TITLE_SEL})[1]/@title').get() or '').strip()

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = (source.xpath(f'({_TITLE_SEL})[1]/@href').get() or '').strip()
        return absolute_url(href, loaded.site.base_url) if href else ''

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        return iso_date((source.xpath('(.//div[@class="-g-vc-item-date"])[1]').xpath('string(.)').get() or '').strip())

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//h1[@class="-mvd-heading"])[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//div[@class="-mvd-description"])[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    def _first_actor(self, scene: LoadedScene) -> str:
        assert scene.sel is not None
        return (scene.sel.xpath('(//div[@class="-mvd-grid-actors"]//span/a)[1]').xpath('string(.)').get() or '').strip()

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return self._first_actor(scene) or None

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        tag = self._first_actor(scene)
        return [tag] if tag else None

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        stats = (scene.sel.xpath('(//div[@class="-mvd-grid-stats"])[1]').xpath('string(.)').get() or '').strip()
        raw = stats.split('•')[-1].strip() if stats else ''
        return (iso_date(raw) if raw else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//span[@class="-mvd-list-item"]/a')]
        return self.dedup_strings(values) or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in scene.sel.xpath('//div[@class="-mvd-grid-actors"]//span/a[@title]'):
            href = (el.xpath('@href').get() or '').strip()
            if not href:
                continue
            page = await self.fetch_and_load(absolute_url(href, base), None, f'GET {href} (actor)')
            if not page:
                continue
            name = (page['sel'].xpath('(//div[@class="-aph-heading"]//h1)[1]').xpath('string(.)').get() or '').strip()
            if not name or name in seen:
                continue
            seen.add(name)
            raw = (page['sel'].xpath('(//div[@class="-api-poster-item"]//img)[1]/@src').get() or '').strip()
            photo = (absolute_url(raw, base)) if raw else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        coll = self.image_collector(lambda raw: absolute_url(raw, scene.site.base_url))
        xpaths = (
            '//picture[@class="-vcc-picture"]//img/@src',
            '//div[@class="swiper-wrapper"]/div/a/div/@data-bg',
        )
        for xpath in xpaths:
            for raw in scene.sel.xpath(xpath).getall():
                coll['push'](raw.strip())
        images: list[str] = coll['list']
        return images or None
