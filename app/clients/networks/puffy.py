from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_attr

STUDIO = 'Puffy Network'
_SEARCH_CARD = '//div[@style="position:relative; background:black;"]'


class PuffyClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {url}')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath(_SEARCH_CARD))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_attr(source, '(.//a)[1]/@title')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//a)[1]/@href')
        return absolute_url(href, loaded.site.base_url) if href else ''

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        return loaded.ctx.search_date

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = (scene.sel.xpath('(//div/section[1]/div[2]/h2/span)[1]').xpath('string(.)').get() or '').strip()

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        all_text = (scene.sel.xpath('(//div/section[3]/div[2])[1]').xpath('string(.)').get() or '').strip()
        if not all_text:
            return
        tags = (scene.sel.xpath('(//div/section[3]/div[2]/p)[1]').xpath('string(.)').get() or '').strip()
        summary = all_text.replace(tags, '') if tags else all_text
        metadata.summary = summary.split('Show more...')[0].strip()

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//div/section[2]/dl/dt[2])[1]').xpath('string(.)').get() or '').replace('Released on:', '').strip()
        if raw:
            metadata.release_date = iso_date(raw)
            return
        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        genres = self.dedup_strings([first_attr(a, 'normalize-space(.)') for a in scene.sel.xpath('//div/section[3]/div[2]/p/a')])
        cast = len(scene.sel.xpath('//div/section[2]/dl/dd[1]/a'))
        if (group := self.group_genre_for(cast)) and group not in genres:
            genres.append(group)
        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        base = scene.site.base_url
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in scene.sel.xpath('//div/section[2]/dl/dd[1]/a'):
            name = first_attr(el, 'normalize-space(.)')
            href = first_attr(el, '@href')
            if not name or name in seen:
                continue
            seen.add(name)
            photo = ''
            if href:
                page = await self.fetch_and_load(absolute_url(href, base), None, f'[{scene.site.name}] actor {name}')
                raw = first_attr(page['sel'], '(//div/section[1]/div/div[1]/img)[1]/@src') if page else ''
                if raw:
                    photo = absolute_url(raw, base)
            actors.append(ActorResult(name=name, photo_url=photo))
        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        base = scene.site.base_url
        images: list[str] = []

        parts = scene.url.split('-video-')
        if len(parts) > 1:
            cover = parts[1]
            host = scene.site.name.lower().replace(' ', '')
            images.append(f'https://media.{host}.com/videos/video-{cover}cover/hd.jpg')

        for raw in scene.sel.xpath('//div[contains(@id,"pics")]//img/@src').getall():
            if not raw:
                continue
            abs_url = absolute_url(raw, base)
            if abs_url not in images:
                images.append(abs_url)
        metadata.raw_image_urls = images
