from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from app.utils.helpers.helpers import absolute_url, append_unique, iso_date
from app.utils.helpers.html_helpers import first_attr, first_text

_ACTOR_XP = '//div/strong[normalize-space(text())="Starring"]/following-sibling::span//a[contains(@class,"tiny-link")]'


class XSinsVRClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = f'{base}{ctx.site_info.search_path}{ctx.title}'
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//div[contains(@class,"tn-video") and contains(@class,"tn-video--horizontal")]'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/a[contains(@class,"tn-video-name")]')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//a[contains(@class,"tn-video-media")]/@href)[1]')
        if not href:
            return ''
        return absolute_url(href, loaded.site.base_url)

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//title')
        metadata.title = (raw.split('•')[0].strip() if raw else '') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        parts = [p.xpath('string(.)').get() or '' for p in scene.sel.xpath('//li/div[contains(@class,"small")]//p')]
        joined = ''.join(parts).strip()
        metadata.summary = joined or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//span//time')
        if raw:
            parsed = iso_date(raw, '%b %d, %Y') or iso_date(raw)
            if parsed:
                metadata.release_date = parsed
                return
        if scene.scene_date:
            metadata.release_date = iso_date(scene.scene_date) or scene.scene_date

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        values: list[str | None] = [el.xpath('normalize-space(.)').get() for el in scene.sel.xpath('//div[contains(@class,"tags-item")]')]
        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        base = scene.site.base_url
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for a in scene.sel.xpath(_ACTOR_XP):
            name = first_attr(a, 'normalize-space(.)')
            href = first_attr(a, '@href')
            if not name or name in seen:
                continue
            seen.add(name)
            photo = ''
            if href:
                url = absolute_url(href, base)
                page = await self.fetch_and_load(url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {name}')
                if page:
                    raw = first_attr(page['sel'], '(//div[contains(@class,"model-header__photo")]//img/@src)[1]')
                    if raw:
                        photo = absolute_url(raw, base)
            actors.append(ActorResult(name=name, photo_url=photo))
        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        base = scene.site.base_url
        images: list[str] = []

        def push(raw: str) -> None:
            append_unique(images, raw, base)

        for src in scene.sel.xpath('//div[contains(@class,"tn-photo__container")]//div//a//div//img/@src').getall():
            if (src or '').startswith('http'):
                push(src.replace('sceneGallerySmall', 'sceneGallery'))
        for poster in scene.sel.xpath('//dl8-video/@poster').getall():
            push(poster)
        metadata.art = images
