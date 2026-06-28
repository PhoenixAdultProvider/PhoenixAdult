from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_text


class ReidMyLipsClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        slug = '-'.join(ctx.title.strip().lower().split())
        scene_url = f'{base}/updates/{slug}.html'
        loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] guess {scene_url}')
        if not loaded:
            return None
        if not first_text(loaded['sel'], '//span[contains(@class,"update_title")]'):
            return None
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=[loaded['sel']], capture=ctx.capture, extra=scene_url)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, '//span[contains(@class,"update_title")]')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        return str(loaded.extra)

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        return iso_date(first_text(source, '//span[contains(@class,"availdate")]'))

    async def fetch_search_score(self, source: Any, loaded: LoadedSearch) -> float | None:
        return 100

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//span[contains(@class,"update_title")]') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//span[contains(@class,"latest_update_description")]') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return 'ReidMyLips'

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//span[contains(@class,"availdate")]')
        return (iso_date(raw) if raw else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//span[contains(@class,"update_tags")]//a')]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        return [ActorResult(name='Riley Reid')]

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        images: list[str] = []
        for raw in scene.sel.xpath('//div[contains(@class,"update_image")]//img/@src0_2x').getall():
            raw = (raw or '').strip()
            if not raw:
                continue
            abs_url = absolute_url(raw, scene.site.base_url)
            if abs_url not in images:
                images.append(abs_url)
        return images
