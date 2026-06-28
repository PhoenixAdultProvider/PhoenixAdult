from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_text

STUDIO = 'SinsLife'

_SUMMARY_XP = '//div[4]/div/div[2]/div/div/div[2]/div[2]/p'
_DATE_XP = '//div[4]/div/div[2]/div/div/div[2]/div[1]/div/div[1]'
_ACTORS_XP = '//div[4]/div/div[2]/div/div/div[2]/div[3]/ul/li'
_POSTER_XP = '//div[4]/div/div[2]/div/div/div[1]/div[2]/div/div[1]/img'
_SEARCH_CARD_XP = '//div[4]/div/div[3]/div/div'


class SinsLifeClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath(_SEARCH_CARD_XP))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return (source.xpath('(.//a/@title)[1]').get() or '').strip()

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = (source.xpath('(.//a/@href)[1]').get() or '').strip()
        if not href:
            return ''
        return absolute_url(href, loaded.site.base_url)

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//div[contains(@class,"section")]//h1') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, _SUMMARY_XP) or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, _DATE_XP)
        if raw.lower().startswith('release date'):
            raw = raw[len('release date') :].lstrip(': ').strip()
        return iso_date(raw, '%B %d, %Y') if raw else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        count = len(scene.sel.xpath(_ACTORS_XP))
        if count == 3:
            return ['Threesome']
        if count == 4:
            return ['Foursome']
        if count > 4:
            return ['Orgy']
        return []

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in scene.sel.xpath(_ACTORS_XP):
            name = (el.xpath('normalize-space(.)').get() or '').strip()
            if name and name not in seen:
                seen.add(name)
                actors.append(ActorResult(name=name))
        return actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        src = (scene.sel.xpath(_POSTER_XP + '/@src').get() or '').strip()
        if not src:
            return []
        return [src if src.startswith('http') else f'https:{src}']
