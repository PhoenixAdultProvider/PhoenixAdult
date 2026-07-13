from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date, to_https
from app.utils.helpers.html_helpers import first_attr, first_text

STUDIO = 'We Are Hairy'
_FIXED_GENRES: list[str] = ['Hairy Girls', 'Hairy Pussy']


class WeAreHairyClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//div[contains(@class,"results")]//ul//li'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/p[contains(@class,"title")]//a')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//div[contains(@class,"top")]//p//a/@href)[1]')
        if not href:
            return ''
        return absolute_url(href, loaded.site.base_url)

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw = first_text(source, './/p[contains(@class,"short")]').replace('Added:', '').strip()
        return iso_date(raw) if raw else None

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        metadata.title = first_text(sel, '//title') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        metadata.summary = first_text(sel, '//div[contains(@class,"desc")]/div[1]//p') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        raw = first_text(sel, '//span[contains(@class,"added")]//time')
        if raw:
            parsed = iso_date(raw, '%b %d, %Y') or iso_date(raw)
            if parsed:
                metadata.release_date = parsed
                return
        if scene.scene_date:
            metadata.release_date = iso_date(scene.scene_date) or scene.scene_date

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        genres = self.dedup_strings([first_attr(el, 'normalize-space(.)') for el in sel.xpath('//div[contains(@class,"tagline")]//p//a')])
        for g in _FIXED_GENRES:
            if g not in genres:
                genres.append(g)
        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for alt in sel.xpath('//div[contains(@class,"meet")]//a//img/@alt').getall():
            name = (alt or '').replace('WeAreHairy.com', '').strip()
            if not name or name in seen:
                continue
            seen.add(name)
            actors.append(ActorResult(name=name))
        metadata.actors = actors

    async def fetch_directors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        entries = [ActorResult(name=(p.xpath('normalize-space(.)').get() or '')) for p in sel.xpath('//div[contains(@class,"desc")]/div[2]//p')]
        directors = self.dedup_people(entries)
        metadata.directors = directors or None

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        coll = self.image_collector(lambda src: to_https((src or '').strip()))
        for src in sel.xpath('//div[contains(@class,"moviemain")]/div[1]//a//img/@src').getall():
            coll['push'](src)
        metadata.art = coll['list']
