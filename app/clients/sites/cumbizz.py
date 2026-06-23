from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url
from app.utils.helpers.html_helpers import first_text


class CumbizzClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        slug = '-'.join(ctx.title.strip().split())
        scene_url = f'{base}/film/{slug}'
        loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] directScene {scene_url}')
        if not loaded:
            return None
        if not first_text(loaded['sel'], '//h1[contains(@class,"har_h1_title")]'):
            return None
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=[loaded['sel']], capture=ctx.capture, extra=scene_url)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, '//h1[contains(@class,"har_h1_title")]')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        return str(loaded.extra)

    async def fetch_search_score(self, source: Any, loaded: LoadedSearch) -> float | None:
        return 90

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//h1[contains(@class,"har_h1_title")]') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//div[contains(@class,"container") and contains(@class,"text-center")]//h2') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return 'Cumbizz'

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        genres: list[str] = []
        for a in scene.sel.xpath('//span[contains(@class,"label-primary")]/a'):
            g = (a.xpath('normalize-space(.)').get() or '').strip().lower()
            if g and g not in genres:
                genres.append(g)
        return genres

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        entries = [ActorResult(name=a.xpath('normalize-space(.)').get() or '') for a in scene.sel.xpath('//div[contains(@class,"breadcrumbs")]/a')]
        return self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        images: list[str] = []

        def add(raw: str) -> None:
            raw = (raw or '').strip()
            if not raw:
                return
            abs_url = raw if raw.startswith('http') else absolute_url(raw, scene.site.base_url)
            if abs_url not in images:
                images.append(abs_url)

        add(scene.sel.xpath('(//section[contains(@class,"har_image_bck")]/@data-image)[1]').get() or '')
        for el in scene.sel.xpath('//img[contains(@class,"vidgal")]'):
            add(el.xpath('@src').get() or '')
        return images
