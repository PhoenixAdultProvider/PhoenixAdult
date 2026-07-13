from __future__ import annotations

import re
from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from app.utils.helpers.helpers import absolute_url, append_unique, iso_date
from app.utils.helpers.html_helpers import first_attr, first_text

_CARD_XP = '//a[contains(@class,"scene") and contains(@class,"item") and contains(@class,"light_background")]'
_IMAGE_RE = re.compile(r'image:\s*"([^"]+)"')


class WakeUpNFuckClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath(_CARD_XP))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        title = first_text(source, './/h3')
        if not title:
            return ''
        actors = first_text(source, './/p[contains(@class,"sub")]')
        return f'{title} [{actors}]' if actors else title

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '@href')
        if not href:
            return ''
        return absolute_url(href, loaded.site.base_url)

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = first_text(scene.sel, '//div[contains(@class,"block")]//h2') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        desc = first_text(scene.sel, '//div[contains(@class,"description")]')
        parts = desc.split('Publish Date :')
        if len(parts) >= 2:
            raw = parts[-1].strip()
            if raw:
                parsed = iso_date(raw, '%d %B %Y') or iso_date(raw)
                if parsed:
                    metadata.release_date = parsed
                    return
        if scene.scene_date:
            metadata.release_date = iso_date(scene.scene_date) or scene.scene_date

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//div[contains(@class,"tags")]//a')]
        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        base = scene.site.base_url
        entries: list[ActorResult] = []
        for el in scene.sel.xpath('//div[contains(@class,"starring")]//a[contains(@class,"item")]'):
            name = first_text(el, './/p')
            src = first_attr(el, '(.//img/@src)[1]')
            photo = (absolute_url(src, base)) if src else ''
            entries.append(ActorResult(name=name, photo_url=photo))
        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        base = scene.site.base_url
        images: list[str] = []

        def push(raw: str) -> None:
            append_unique(images, raw, base)

        for poster in scene.sel.xpath('//video[contains(@class,"player_video")]/@poster').getall():
            push(poster)
        if not images:
            for script in scene.sel.xpath('//script/text()').getall():
                m = _IMAGE_RE.search(script)
                if m:
                    push(m.group(1).strip())
        metadata.raw_image_urls = images
