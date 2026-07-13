from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_attr, first_text

STUDIO = 'VIPissy'
_SEARCH_ROW_XP = '//div[contains(@style,"position:relative") and contains(@style,"background:black")]'
_TITLE_XP = '//section[contains(@class,"downloads")]//strong'
_SUMMARY_BLOCK_XP = '//section[4]/div'
_TAGS_BLOCK_XP = '//section[4]/div/p'
_TAGS_LINK_XP = '//section[4]/div/p//a'
_DATE_XP = '//section[2]//dl//dd[2]'
_ACTORS_XP = '//section[2]//dl//dd[1]//a'
_ACTOR_PHOTO_XP = '//section[1]/div/div[1]/img/@src'
_POSTERS_XP = '//div[contains(@id,"pics2")]//div//ul//li//div//div//img/@src'


class VIPissyClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath(_SEARCH_ROW_XP))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_attr(source, '(.//a/@title)[1]')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//a/@href)[1]')
        if not href:
            return ''
        return absolute_url(href, loaded.site.base_url)

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw = first_text(source, './/span[contains(@class,"date")]')
        return iso_date(raw) if raw else None

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = first_text(scene.sel, _TITLE_XP) or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        all_text = first_text(scene.sel, _SUMMARY_BLOCK_XP)
        if not all_text:
            return
        tags = first_text(scene.sel, _TAGS_BLOCK_XP)
        summary = all_text.replace(tags, '').strip() if tags else all_text
        metadata.summary = summary.split('Show more...')[0].strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = first_text(scene.sel, _DATE_XP)
        if raw:
            parsed = iso_date(raw, '%b %d, %Y') or iso_date(raw)
            if parsed:
                metadata.release_date = parsed
                return
        if scene.scene_date:
            metadata.release_date = iso_date(scene.scene_date) or scene.scene_date

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        genres: list[str] = []
        for el in scene.sel.xpath(_TAGS_LINK_XP):
            t = first_attr(el, 'normalize-space(.)').lower()
            if t and t not in genres:
                genres.append(t)
        count = len(scene.sel.xpath(_ACTORS_XP))
        if (group := self.group_genre_for(count)) and group not in genres:
            genres.append(group)
        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        base = scene.site.base_url
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for a in scene.sel.xpath(_ACTORS_XP):
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
                    raw = (page['sel'].xpath(f'({_ACTOR_PHOTO_XP})[1]').get() or '').strip()
                    if raw:
                        photo = absolute_url(raw, base)
            actors.append(ActorResult(name=name, photo_url=photo))
        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        base = scene.site.base_url
        images: list[str] = []
        for raw in scene.sel.xpath(_POSTERS_XP).getall():
            raw = (raw or '').strip()
            if not raw:
                continue
            abs_url = absolute_url(raw, base)
            if abs_url not in images:
                images.append(abs_url)
        idx = scene.url.find('/updates')
        if idx >= 0:
            twitter_bg = f'https://media.vipissy.com/videos{scene.url[idx + len("/updates") :]}cover/l.jpg'
            if twitter_bg not in images:
                images.insert(0, twitter_bg)
        metadata.raw_image_urls = images
