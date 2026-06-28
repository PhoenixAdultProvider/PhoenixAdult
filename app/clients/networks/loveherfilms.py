from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_attr

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
        return first_attr(source, '(.//a)[1]/@title')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//a)[1]/@href')
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
        genres = self.dedup_strings([first_attr(a, 'normalize-space(.)') for a in scene.sel.xpath('//div[contains(@class,"video-tags")]/a')])
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
            name = first_attr(a, 'normalize-space(.)')
            href = first_attr(a, '@href')
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
                url = absolute_url(href, base)
                page = await self.fetch_and_load(url, None, f'[{scene.site.name}] actor {name}')
                raw = first_attr(page['sel'], '(//div[contains(@class,"picture")]//img)[1]/@src0_3x') if page else ''
                if raw:
                    photo = absolute_url(raw, base)
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        coll = self.image_collector(lambda raw: absolute_url(raw, base))
        xpaths = (
            '//meta[@property="og:image"]/@content',
            '//div[contains(@class,"photos")]//a//img/@src',
        )
        for xpath in xpaths:
            for raw in scene.sel.xpath(xpath).getall():
                coll['push'](raw)
        images: list[str] = coll['list']
        return images or None
