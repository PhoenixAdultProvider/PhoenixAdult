from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneContext, SearchContext
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.processors.title_case import title_case

STUDIO = 'New Sensations'


class NewSensationsOtherClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        encoded = ctx.title.strip().lower().replace(' ', '+')
        url = base + ctx.site_info.search_path.replace('{query}', encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {url}')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//div[@class="update_details"]'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return (source.xpath('(.//a)[1]').xpath('string(.)').get() or '').strip()

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = (source.xpath('(.//a)[1]/@href').get() or '').strip()
        return absolute_url(href, loaded.site.base_url) if href else ''

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        tok = (source.xpath('(.//div[@class="date_small"])[1]').xpath('string(.)').get() or '').split(':')[-1].strip()
        return iso_date(tok, '%m/%d/%Y') if tok else None

    # ── Context loader (resolves cast + keeps the last actor page) ──────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        pipe = payload.find('|')
        url = payload[:pipe] if pipe >= 0 else payload
        fallback = payload[pipe + 1 :].strip() if pipe >= 0 else None
        capture = ctx.capture if ctx else None

        loaded = await self.fetch_and_load(url, FetchCtx(capture=capture), f'[{site.name}] scene {url}')
        if not loaded:
            return None

        actors: list[ActorResult] = []
        last_actor_page: Any = None
        seen: set[str] = set()
        for el in loaded['sel'].xpath('//span[@class="update_models"]/a'):
            name = (el.xpath('normalize-space(.)').get() or '').strip()
            if not name or name in seen:
                continue
            seen.add(name)
            photo = ''
            href = (el.xpath('@href').get() or '').strip()
            if href:
                page = await self.fetch_and_load(absolute_url(href, site.base_url), FetchCtx(capture=capture), f'GET {href} (actor)')
                if page:
                    last_actor_page = page['sel']
                    raw = (page['sel'].xpath('(//div[contains(@class,"cell_top") and contains(@class,"cell_thumb")]/img)[1]/@src0_1x').get() or '').strip()
                    if raw:
                        photo = raw if raw.startswith('http') else absolute_url(raw, site.base_url)
            actors.append(ActorResult(name=name, photo_url=photo))

        return LoadedScene(
            url=url,
            site=site,
            scene_date=fallback or None,
            capture=capture,
            sel=loaded['sel'],
            html=loaded['html'],
            extra={'actors': actors, 'last_actor_page': last_actor_page},
        )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//div[@class="update_title"])[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//span[@class="update_description"])[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        return scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [
            title_case((a.xpath('normalize-space(.)').get() or '').replace('-', '')) for a in scene.sel.xpath('//span[@class="update_tags"]/a')
        ]
        return self.dedup_strings(values) or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        actors = (scene.extra or {}).get('actors') or []
        return actors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        images: list[str] = []

        def push(raw: str) -> None:
            trimmed = (raw or '').strip()
            if not trimmed:
                return
            abs_url = trimmed if trimmed.startswith('http') else absolute_url(trimmed, base)
            if abs_url not in images:
                images.append(abs_url)

        for src in scene.sel.xpath('//div[contains(@class,"mejs-layers")]//img/@src').getall():
            push(src)

        last = (scene.extra or {}).get('last_actor_page')
        if last is not None:
            title = (scene.sel.xpath('(//div[@class="update_title"])[1]').xpath('string(.)').get() or '').strip().lower()
            for block in last.xpath('//div[contains(@class,"table") and contains(@class,"dvd_info")]'):
                block_title = (block.xpath('(.//div[@class="update_title"])[1]').xpath('string(.)').get() or '').strip().lower()
                if block_title != title:
                    continue
                for src in block.xpath('.//div[@class="cell"]//img/@src0_3x').getall():
                    push(src)
        return images or None
