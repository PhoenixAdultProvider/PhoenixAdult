from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date

STUDIO = 'LoveHerFilms'
_DATE_FMT = '%B %d, %Y'


class LoveHerFilmsClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {url}')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//div[contains(@class,"item-video-overlay")]'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return (source.xpath('(.//a)[1]/@title').get() or '').strip()

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = (source.xpath('(.//a)[1]/@href').get() or '').strip()
        return absolute_url(href, loaded.site.base_url) if href else ''

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw = (source.xpath('(.//p[contains(@class,"video-date")])[1]').xpath('string(.)').get() or '').strip()
        return (iso_date(raw) if raw else None) or loaded.ctx.search_date

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//div[contains(@class,"main-info-left")]/h1)[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//p[contains(@class,"description")])[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//div[contains(@class,"date")])[1]').xpath('string(.)').get() or '').strip()
        if raw:
            return iso_date(raw, _DATE_FMT)
        return (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        genres: list[str] = []
        for a in scene.sel.xpath('//div[contains(@class,"video-tags")]/a'):
            g = (a.xpath('normalize-space(.)').get() or '').strip()
            if g and g not in genres:
                genres.append(g)
        if 'Foot Sex' not in genres:
            genres.append('Foot Sex')
        cast = len(scene.sel.xpath('//div[contains(@class,"featured")]/a'))
        if cast == 3 and 'Threesome' not in genres:
            genres.append('Threesome')
        elif cast == 4 and 'Foursome' not in genres:
            genres.append('Foursome')
        elif cast > 4 and 'Orgy' not in genres:
            genres.append('Orgy')
        return genres

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        refs: list[tuple[str, str]] = []
        for a in scene.sel.xpath('//div[contains(@class,"featured")]/a'):
            name = (a.xpath('normalize-space(.)').get() or '').strip()
            href = (a.xpath('@href').get() or '').strip()
            if name:
                refs.append((name, href))
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for name, href in refs:
            if name in seen:
                continue
            seen.add(name)
            photo = ''
            if href:
                url = href if href.startswith('http') else absolute_url(href, base)
                page = await self.fetch_and_load(url, None, f'[{scene.site.name}] actor {name}')
                raw = (page['sel'].xpath('(//div[contains(@class,"picture")]//img)[1]/@src0_3x').get() or '').strip() if page else ''
                if raw:
                    photo = raw if raw.startswith('http') else absolute_url(raw, base)
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        coll = self.image_collector(lambda raw: raw if raw.startswith('http') else absolute_url(raw, base))
        xpaths = (
            '//meta[@property="og:image"]/@content',
            '//div[contains(@class,"photos")]//a//img/@src',
        )
        for xpath in xpaths:
            for raw in scene.sel.xpath(xpath).getall():
                coll['push'](raw)
        images: list[str] = coll['list']
        return images or None
