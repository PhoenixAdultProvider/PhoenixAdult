from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, load_site_json
from app.utils.helpers.html_helpers import first_text

STUDIO = 'Joymii'
TAGLINE = 'Step Secrets'

_FIXED_GENRES: list[str] = load_site_json(__file__, 'stepsecrets_fixed_genres')


class StepSecretsClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//div[contains(@class,"card-simple")]'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/a[contains(@class,"color-title")]')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = (source.xpath('(.//a/@href)[1]').get() or '').strip()
        if not href:
            return ''
        return href if href.startswith('http') else absolute_url(href, loaded.site.base_url)

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//h1[contains(@class,"font-cond")]') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//div[contains(@class,"descripton")]') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return TAGLINE

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [TAGLINE]

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        return list(_FIXED_GENRES)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for href in scene.sel.xpath('//p[contains(@class,"mb-2")]//a/@href').getall():
            href = (href or '').strip()
            if not href:
                continue
            actor_url = href if href.startswith('http') else absolute_url(href, base)
            page = await self.fetch_and_load(actor_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {actor_url}')
            if not page:
                continue
            name = first_text(page['sel'], '//h1[contains(@class,"font-cond")]')
            if not name or name in seen:
                continue
            seen.add(name)
            raw = (page['sel'].xpath('(//div[contains(@class,"model-about")]//img/@src)[1]').get() or '').strip()
            photo = raw.split('?')[0] if raw else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        images: list[str] = []
        for src in scene.sel.xpath('//video/@poster').getall():
            s = (src or '').strip()
            if s and s not in images:
                images.append(s)
        for src in scene.sel.xpath('//div[@id="photoCarousel"]//img/@src').getall():
            s = (src or '').strip()
            if s and s not in images:
                images.append(s)
        return images
