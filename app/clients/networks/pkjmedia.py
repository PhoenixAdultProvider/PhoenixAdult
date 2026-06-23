from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date

STUDIO = 'PKJ Media'

_DATA = Path(__file__).parent / '_data' / 'json'
_GENRES: dict[str, list[str]] = json.loads((_DATA / 'pkjmedia_genres.json').read_text(encoding='utf-8'))


class PKJMediaClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {url}')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//ul[contains(@class,"bricks-layout-wrapper")]//div[contains(@class,"bricks-layout-inner")]//h3/a'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return (source.xpath('normalize-space(.)').get() or '').strip()

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = (source.xpath('@href').get() or '').strip()
        return absolute_url(href, loaded.site.base_url) if href else ''

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        return loaded.ctx.search_date

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//h1[contains(@class,"brxe-post-title")])[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        span = (scene.sel.xpath('(//div[contains(@class,"brxe-post-content")]//p//span)[1]').xpath('string(.)').get() or '').strip()
        if span:
            return span
        return (scene.sel.xpath('(//div[contains(@class,"brxe-post-content")]//p)[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        return (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        return _GENRES.get(scene.site.name) or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        entries = [
            ActorResult(name=(a.xpath('normalize-space(.)').get() or '').strip()) for a in scene.sel.xpath('//div[contains(@class,"brxe-post-meta")]//span/a')
        ]
        return self.dedup_people(entries) or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        coll = self.image_collector(lambda raw: raw if raw.startswith('http') else absolute_url(raw, scene.site.base_url))
        for poster in scene.sel.xpath('//video[contains(@class,"bricks-plyr")]/@poster').getall():
            coll['push'](poster)
        images: list[str] = coll['list']
        return images or None
