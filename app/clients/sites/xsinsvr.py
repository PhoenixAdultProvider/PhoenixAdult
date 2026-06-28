from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_text

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
        href = (source.xpath('(.//a[contains(@class,"tn-video-media")]/@href)[1]').get() or '').strip()
        if not href:
            return ''
        return absolute_url(href, loaded.site.base_url)

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//title')
        return raw.split('•')[0].strip() or None if raw else None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        parts = [p.xpath('string(.)').get() or '' for p in scene.sel.xpath('//li/div[contains(@class,"small")]//p')]
        joined = ''.join(parts).strip()
        return joined or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//span//time')
        if raw:
            parsed = iso_date(raw, '%b %d, %Y') or iso_date(raw)
            if parsed:
                return parsed
        if scene.scene_date:
            return iso_date(scene.scene_date) or scene.scene_date
        return None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [el.xpath('normalize-space(.)').get() for el in scene.sel.xpath('//div[contains(@class,"tags-item")]')]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for a in scene.sel.xpath(_ACTOR_XP):
            name = (a.xpath('normalize-space(.)').get() or '').strip()
            href = (a.xpath('@href').get() or '').strip()
            if not name or name in seen:
                continue
            seen.add(name)
            photo = ''
            if href:
                url = absolute_url(href, base)
                page = await self.fetch_and_load(url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {name}')
                if page:
                    raw = (page['sel'].xpath('(//div[contains(@class,"model-header__photo")]//img/@src)[1]').get() or '').strip()
                    if raw:
                        photo = absolute_url(raw, base)
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        images: list[str] = []

        def push(raw: str) -> None:
            raw = (raw or '').strip()
            if not raw:
                return
            abs_url = absolute_url(raw, base)
            if abs_url not in images:
                images.append(abs_url)

        for src in scene.sel.xpath('//div[contains(@class,"tn-photo__container")]//div//a//div//img/@src').getall():
            if (src or '').startswith('http'):
                push(src.replace('sceneGallerySmall', 'sceneGallery'))
        for poster in scene.sel.xpath('//dl8-video/@poster').getall():
            push(poster)
        return images
