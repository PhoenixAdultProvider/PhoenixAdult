from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_text
from app.utils.processors.title_case import title_case

_CARD_XP = '//div[contains(concat(" ", normalize-space(@class), " "), " item ")]'
_INFO_LI = '//ul[contains(@class,"more-info")]/li'


class ScrewboxClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath(_CARD_XP))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/h4//a')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = (source.xpath('(.//a/@href)[1]').get() or '').strip()
        return absolute_url(href, loaded.site.base_url) if href else ''

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//div[contains(@class,"item-details-right")]//h1') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//p[contains(@class,"shorter")]') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return 'Screwbox'

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return ['Screwbox']

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, f'({_INFO_LI})[2]').replace('RELEASE DATE:', '').strip()
        return (iso_date(raw) if raw else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [title_case(a.xpath('normalize-space(.)').get() or '') for a in scene.sel.xpath(f'({_INFO_LI})[3]//a')]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in scene.sel.xpath(f'({_INFO_LI})[1]//a'):
            name = title_case((el.xpath('normalize-space(.)').get() or '').strip())
            if not name or name in seen:
                continue
            seen.add(name)
            photo = ''
            href = (el.xpath('@href').get() or '').strip()
            if href:
                loaded = await self.fetch_and_load(absolute_url(href, scene.site.base_url), FetchCtx(capture=scene.capture), f'GET {href} (actor)')
                raw = (loaded['sel'].xpath('(//img[contains(@class,"model_bio_thumb")]/@src0_1x)[1]').get() or '').strip() if loaded else ''
                photo = (raw if raw.startswith('http') else absolute_url(raw, scene.site.base_url)) if raw else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//div[contains(@class,"fakeplayer")]//img/@src0_1x)[1]').get() or '').strip()
        if not raw:
            return []
        return [raw if raw.startswith('http') else absolute_url(raw, scene.site.base_url)]
