from __future__ import annotations

from typing import Any
from urllib.parse import quote

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from app.utils.helpers.helpers import absolute_url
from app.utils.helpers.html_helpers import first_attr, first_text

# `div.update` cards must match the class token exactly (updateTitle, updateDescription, etc. all contain "update").
_UPDATE_CARD_XP = '//div[contains(concat(" ", normalize-space(@class), " "), " update ")]'


class BoundHoneysClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', quote(ctx.title, safe=''))
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath(_UPDATE_CARD_XP))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/div[contains(@class,"updateTitle")]')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//div[contains(@class,"updateTitle")]//a/@href)[1]')
        if not href:
            return ''
        return absolute_url(href, loaded.site.base_url)

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = first_text(scene.sel, '//div[contains(@class,"updateVideoTitle")]') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = first_text(scene.sel, '//div[contains(@class,"updateDescription")]//b') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'Bound Honeys'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def _collect_actors(self, scene: LoadedScene) -> list[ActorResult]:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in scene.sel.xpath('//div[contains(@class,"updateModelsList")]//a'):
            name = first_attr(el, 'normalize-space(.)')
            href = first_attr(el, '@href')
            if not name or not href or name in seen:
                continue
            seen.add(name)
            actor_url = absolute_url(href, scene.site.base_url)
            actor_page = await self.fetch_and_load(actor_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {name}')
            photo = ''
            if actor_page:
                raw = first_attr(actor_page['sel'], '(//div[contains(@class,"modelDetailPhoto")]//img/@src)[1]')
                photo = absolute_url(raw, scene.site.base_url) if raw else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        genres = self.dedup_strings([first_attr(a, 'normalize-space(.)') for a in scene.sel.xpath('//div[contains(@class,"updateCategoriesList")]//a')])
        n = len(await self._collect_actors(scene))
        if group := self.group_genre_for(n):
            genres.append(group)
        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.actors = await self._collect_actors(scene)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        images: list[str] = []
        for href in scene.sel.xpath('//link[@rel="preload"]/@href').getall():
            href = (href or '').strip()
            if not href:
                continue
            abs_url = absolute_url(href, scene.site.base_url)
            if abs_url not in images:
                images.append(abs_url)
        metadata.raw_image_urls = images
