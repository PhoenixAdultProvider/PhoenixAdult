from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_attr, first_text

STUDIO = 'FuckingAwesome'
_ACTOR_XP = '//div[contains(@class,"pornstarnames")]//ul//li//a[contains(@href,"pornstars")]'


class FuckingAwesomeClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//div[contains(@class,"gallery")]/div'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/div[contains(@class,"video-title") and contains(@class,"truncate")]/a')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//div[contains(@class,"video-title") and contains(@class,"truncate")]/a/@href)[1]')
        if not href:
            return ''
        return absolute_url(href, loaded.site.base_url)

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw = first_text(source, './/span[contains(@class,"small") and contains(@class,"date")]')
        return iso_date(raw) if raw else None

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = first_text(scene.sel, '//h1') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = first_text(scene.sel, '//div[contains(@class,"more") and contains(@class,"text-justify")]') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//div[contains(@class,"videodate")]//strong')
        metadata.release_date = iso_date(raw, '%B %d, %Y') or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        genres: list[str] = []
        for a in scene.sel.xpath('//div[contains(@class,"tags")]//ul//li//a'):
            g = first_attr(a, 'normalize-space(.)').lower()
            if g and g not in genres:
                genres.append(g)
        count = len(scene.sel.xpath(_ACTOR_XP))
        if (group := self.group_genre_for(count)) and group not in genres:
            genres.append(group)
        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in scene.sel.xpath(_ACTOR_XP):
            name = first_attr(el, 'normalize-space(.)')
            href = first_attr(el, '@href')
            if not name or not href or name in seen:
                continue
            seen.add(name)
            actor_url = absolute_url(href, scene.site.base_url)
            actor_page = await self.fetch_and_load(actor_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {name}')
            photo = ''
            if actor_page:
                src = first_attr(actor_page['sel'], '(//div[contains(@class,"pornstar-pic")]//img/@src)[1]')
                photo = absolute_url(src, scene.site.base_url) if src else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        base = scene.site.base_url.rstrip('/')
        coll = self.image_collector(lambda raw: absolute_url((raw or '').strip(), base))

        for raw in scene.sel.xpath('//span[contains(@class,"et_pb_image_wrap")]//img/@content').getall():
            coll['push'](raw)

        photos_href = first_attr(scene.sel, '(//li[contains(@class,"photos")]//a/@href)[1]')
        if photos_href:
            photos_url = absolute_url(photos_href, scene.site.base_url)
            photos_page = await self.fetch_and_load(photos_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] photos page')
            if photos_page:
                for raw in photos_page['sel'].xpath('//div[contains(@class,"my-gallery")]//a/@href').getall():
                    coll['push'](raw)
        metadata.raw_image_urls = coll['list']
