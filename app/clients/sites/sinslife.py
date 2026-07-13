from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_attr, first_text

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
        return first_attr(source, '(.//a/@title)[1]')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//a/@href)[1]')
        if not href:
            return ''
        return absolute_url(href, loaded.site.base_url)

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = first_text(scene.sel, '//div[contains(@class,"section")]//h1') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = first_text(scene.sel, _SUMMARY_XP) or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = first_text(scene.sel, _DATE_XP)
        if raw.lower().startswith('release date'):
            raw = raw[len('release date') :].lstrip(': ').strip()
        metadata.release_date = iso_date(raw, '%B %d, %Y') if raw else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        count = len(scene.sel.xpath(_ACTORS_XP))
        group = self.group_genre_for(count)
        metadata.genres = [group] if group else []

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in scene.sel.xpath(_ACTORS_XP):
            name = first_attr(el, 'normalize-space(.)')
            if name and name not in seen:
                seen.add(name)
                actors.append(ActorResult(name=name))
        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        src = (scene.sel.xpath(_POSTER_XP + '/@src').get() or '').strip()
        if not src:
            return
        metadata.art = [src if src.startswith('http') else f'https:{src}']
