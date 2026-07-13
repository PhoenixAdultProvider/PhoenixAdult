from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_attr, first_text

_FIXED_GENRES: list[str] = ['BDSM', 'Breast Torture', 'Breasts', 'Fetish', 'HuCows', 'Nipple Torture', 'Nipples']


class HucowsClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        if ctx.search_date:
            y, m = ctx.search_date.split('-')[:2]
            url = f'{base}/{y}/{m}'
        else:
            url = f'{base}/?s={ctx.title.strip().replace(" ", "+")}'
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {url}')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//article'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, '(.//h1|.//h2)')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//a/@href)[2]')
        if not href:
            return ''
        return absolute_url(href, loaded.site.base_url)

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw = first_text(source, './/div[@itemprop="datePublished"]')
        return iso_date(raw) if raw else None

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//head//title').replace(' - HuCows.com', '').strip()
        metadata.title = raw or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = first_text(scene.sel, '//article//div[contains(@class,"entry-content")]//p') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'HuCows'

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = ['HuCows']

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//div[@itemprop="datePublished"]').replace('Release Date:', '').strip()
        metadata.release_date = (iso_date(raw, '%d %b %Y') if raw else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        genres = list(_FIXED_GENRES)
        for a in scene.sel.xpath('//a[@rel="category tag"]'):
            g = first_attr(a, 'normalize-space(.)')
            if g and g not in genres:
                genres.append(g)
        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        entries = [ActorResult(name=a.xpath('normalize-space(.)').get() or '') for a in scene.sel.xpath('//a[@rel="tag"]')]
        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        coll = self.image_collector(lambda raw: absolute_url(raw.strip(), scene.site.base_url))
        for raw in scene.sel.xpath('//article//div//a[contains(@class,"lightboxhover")]//img/@src').getall():
            coll['push'](raw)
        for raw in scene.sel.xpath('//center//a//img[contains(@class,"lightboxhover")]/@src').getall():
            coll['push'](raw)
        metadata.art = coll['list']
