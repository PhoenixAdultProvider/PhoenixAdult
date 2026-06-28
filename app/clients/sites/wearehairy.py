from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date, load_site_json, to_https
from app.utils.helpers.html_helpers import first_text

STUDIO = 'We Are Hairy'
_FIXED_GENRES: list[str] = load_site_json(__file__, 'wearehairy_fixed_genres')


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
        href = (source.xpath('(.//div[contains(@class,"top")]//p//a/@href)[1]').get() or '').strip()
        if not href:
            return ''
        return absolute_url(href, loaded.site.base_url)

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw = first_text(source, './/p[contains(@class,"short")]').replace('Added:', '').strip()
        return iso_date(raw) if raw else None

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//title') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//div[contains(@class,"desc")]/div[1]//p') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//span[contains(@class,"added")]//time')
        if raw:
            parsed = iso_date(raw, '%b %d, %Y') or iso_date(raw)
            if parsed:
                return parsed
        if scene.scene_date:
            return iso_date(scene.scene_date) or scene.scene_date
        return None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        genres: list[str] = []
        for el in scene.sel.xpath('//div[contains(@class,"tagline")]//p//a'):
            t = (el.xpath('normalize-space(.)').get() or '').strip()
            if t and t not in genres:
                genres.append(t)
        for g in _FIXED_GENRES:
            if g not in genres:
                genres.append(g)
        return genres

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for alt in scene.sel.xpath('//div[contains(@class,"meet")]//a//img/@alt').getall():
            name = (alt or '').replace('WeAreHairy.com', '').strip()
            if not name or name in seen:
                continue
            seen.add(name)
            actors.append(ActorResult(name=name))
        return actors

    async def fetch_directors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        entries = [ActorResult(name=(p.xpath('normalize-space(.)').get() or '')) for p in scene.sel.xpath('//div[contains(@class,"desc")]/div[2]//p')]
        directors = self.dedup_people(entries)
        return directors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        images: list[str] = []
        for src in scene.sel.xpath('//div[contains(@class,"moviemain")]/div[1]//a//img/@src').getall():
            url = to_https((src or '').strip())
            if url and url not in images:
                images.append(url)
        return images
