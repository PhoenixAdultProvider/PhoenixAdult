from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, relative_iso_date
from app.utils.helpers.html_helpers import first_attr, first_text


class CumLouderClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//div[contains(@class,"listado-escenas")]//div[contains(@class,"medida")]/a'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/h2')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '@href')
        if not href:
            return ''
        return absolute_url(href, loaded.site.base_url)

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//h1') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//div[@id="content-more-less"]/p') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return 'CumLouder'

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//div[contains(@class,"added")]')
        return relative_iso_date(raw) if raw else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        genres = self.dedup_strings([first_attr(a, 'normalize-space(.)') for a in scene.sel.xpath('//ul[contains(@class,"tags")]/li/a')])
        actor_count = len(scene.sel.xpath('//a[contains(@class,"pornstar-link")]'))
        if actor_count == 3 and 'Threesome' not in genres:
            genres.append('Threesome')
        elif actor_count == 4 and 'Foursome' not in genres:
            genres.append('Foursome')
        elif actor_count > 4 and 'Orgy' not in genres:
            genres.append('Orgy')
        return genres

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        entries = [ActorResult(name=a.xpath('normalize-space(.)').get() or '') for a in scene.sel.xpath('//a[contains(@class,"pornstar-link")]')]
        return self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        images: list[str] = []
        for el in scene.sel.xpath('//div[contains(@class,"box-video-html5")]/video'):
            raw = first_attr(el, '@lazy')
            if not raw:
                continue
            abs_url = absolute_url(raw, scene.site.base_url)
            if abs_url not in images:
                images.append(abs_url)
        return images
