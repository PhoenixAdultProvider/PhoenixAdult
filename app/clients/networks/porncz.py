from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_attr

STUDIO = 'PornCZ'
_DOLLS_SITE = 'Czech Real Dolls'


class PornCZClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        slug = ctx.title.strip().lower().replace(' ', '+').replace('--', '+')
        url = base + ctx.site_info.search_path.replace('{query}', slug)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {url}')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//div[contains(@class,"card--item")]'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return (source.xpath('(.//div[contains(@class,"card-body")]/a)[1]').xpath('string(.)').get() or '').strip()

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//div[contains(@class,"card-body")]/a)[1]/@href')
        return absolute_url(href, loaded.site.base_url) if href else ''

    async def fetch_search_thumb_url(self, source: Any, loaded: LoadedSearch) -> str | None:
        thumb = first_attr(source, '(.//div[contains(@class,"card__img")]//img)[1]/@data-src')
        if not thumb:
            return None
        return absolute_url(thumb, loaded.site.base_url)

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = (scene.sel.xpath('(//h1)[1]').xpath('string(.)').get() or '').strip()

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = (scene.sel.xpath('(//div[contains(@class,"dmb-1")]/p)[1]').xpath('string(.)').get() or '').strip()

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = first_attr(scene.sel, '(//meta[@property="video:release_date"])[1]/@content')
        if raw:
            metadata.release_date = iso_date(raw, '%d.%m.%Y')
            return
        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        values: list[str | None] = [
            (a.xpath('string(.)').get() or '').split('#')[-1].strip()
            for a in scene.sel.xpath('//div[contains(@class,"video-info")]//a[contains(@href,"?category=")]')
        ]
        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        base = scene.site.base_url
        is_dolls = scene.site.name == _DOLLS_SITE
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in scene.sel.xpath('//div[contains(@class,"mini-avatars")]/a'):
            name = first_attr(el, 'normalize-space(.)')
            href = first_attr(el, '@href')
            if not name or name in seen:
                continue
            seen.add(name)
            photo = ''
            gender = ''
            if href:
                page = await self.fetch_and_load(absolute_url(href, base), None, f'[{scene.site.name}] actor {name}')
                if page:
                    raw = first_attr(page['sel'], '(//img[contains(@class,"actor-img")])[1]/@data-src')
                    if raw and 'blank' not in raw:
                        photo = absolute_url(raw, base)
                    gender = (page['sel'].xpath('(//div[contains(@class,"model-info__item")]//span[i])[1]').xpath('string(.)').get() or '').lower().strip()
            display = f'{name} (Sex Doll)' if is_dolls and gender == 'female' else name
            actors.append(ActorResult(name=display, photo_url=photo, gender=gender))
        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        coll = self.image_collector(lambda raw: absolute_url(raw, scene.site.base_url))
        xpaths = (
            '//a[contains(@class,"gallery-popup")]/@href',
            '//video[contains(@class,"video-player")]/@data-poster',
        )
        for xpath in xpaths:
            for raw in scene.sel.xpath(xpath).getall():
                coll['push'](raw)
        images: list[str] = coll['list']
        metadata.raw_image_urls = images
