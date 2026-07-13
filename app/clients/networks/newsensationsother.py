from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneContext, SceneDetail, SearchContext
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_attr
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
        href = first_attr(source, '(.//a)[1]/@href')
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
            name = first_attr(el, 'normalize-space(.)')
            if not name or name in seen:
                continue
            seen.add(name)
            photo = ''
            href = first_attr(el, '@href')
            if href:
                page = await self.fetch_and_load(absolute_url(href, site.base_url), FetchCtx(capture=capture), f'GET {href} (actor)')
                if page:
                    last_actor_page = page['sel']
                    raw = first_attr(page['sel'], '(//div[contains(@class,"cell_top") and contains(@class,"cell_thumb")]/img)[1]/@src0_1x')
                    if raw:
                        photo = absolute_url(raw, site.base_url)
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

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        metadata.title = (sel.xpath('(//div[@class="update_title"])[1]').xpath('string(.)').get() or '').strip()

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        metadata.summary = (sel.xpath('(//span[@class="update_description"])[1]').xpath('string(.)').get() or '').strip()

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        values: list[str | None] = [
            title_case((a.xpath('normalize-space(.)').get() or '').replace('-', '')) for a in sel.xpath('//span[@class="update_tags"]/a')
        ]
        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.actors = (scene.extra or {}).get('actors') or []

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        base = scene.site.base_url
        coll = self.image_collector(lambda raw: absolute_url(raw.strip(), base))

        for src in sel.xpath('//div[contains(@class,"mejs-layers")]//img/@src').getall():
            coll['push'](src)

        last = (scene.extra or {}).get('last_actor_page')
        if last is not None:
            title = (sel.xpath('(//div[@class="update_title"])[1]').xpath('string(.)').get() or '').strip().lower()
            for block in last.xpath('//div[contains(@class,"table") and contains(@class,"dvd_info")]'):
                block_title = (block.xpath('(.//div[@class="update_title"])[1]').xpath('string(.)').get() or '').strip().lower()
                if block_title != title:
                    continue
                for src in block.xpath('.//div[@class="cell"]//img/@src0_3x').getall():
                    coll['push'](src)
        metadata.art = coll['list']
