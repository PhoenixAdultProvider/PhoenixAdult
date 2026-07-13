from __future__ import annotations

from urllib.parse import urlsplit

from parsel import Selector

from app.clients.base import Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, css_bg_image, iso_date, slugify
from app.utils.helpers.html_helpers import first_attr, first_text
from app.utils.logging.best_effort import best_effort
from app.utils.searchengines import SearchOptions, web_search

_DATE_XP = (
    '//span[contains(@class,"date-display-single")]'
    ' | //span[contains(@class,"u-inline-block") and contains(@class,"u-mr--nine")]'
    ' | //div[contains(@class,"video-meta-date")]'
    ' | //div[contains(@class,"date")]'
)


class LustRealityClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        candidates = [f'{base}{ctx.site_info.search_path}{slugify(ctx.title)}']
        host = urlsplit(ctx.site_info.base_url).hostname or ''
        with best_effort(ctx.site_info.name, 'webSearch'):
            for url in await web_search(SearchOptions(query=ctx.title, site=host, num=10)):
                if '/scene/' in url and url not in candidates:
                    candidates.append(url)

        for scene_url in candidates:
            loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] {scene_url}')
            if not loaded:
                continue
            title = first_text(loaded['sel'], '//h1')
            if not title:
                continue
            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=ctx.title,
                    display_date=iso_date(first_text(loaded['sel'], _DATE_XP)),
                    search_date=ctx.search_date,
                )
            )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = first_text(scene.sel, '//h1') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = first_text(scene.sel, '//div[contains(@class,"u-mb--six")]') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.release_date = iso_date(first_text(scene.sel, _DATE_XP)) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//a[contains(@href,"/list/category/")]')]
        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            raw = first_attr(sel, '(//div[contains(@class,"u-ratio--model-poster")]//img/@data-src)[1]')
            return absolute_url(raw, base) if raw else ''

        refs: list[tuple[str, str]] = []
        for el in scene.sel.xpath('//a[contains(@href,"/pornstars/model/")]'):
            name = first_attr(el, 'normalize-space(.)')
            if not name:
                continue
            href = first_attr(el, '@href')
            refs.append((name, absolute_url(href, base) if href else ''))
        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        coll = self.image_collector(lambda raw: absolute_url(raw.strip(), scene.site.base_url))
        for el in scene.sel.xpath('//div[contains(@class,"splash-screen")]'):
            coll['push'](css_bg_image(el.xpath('@style').get()))
        for href in scene.sel.xpath('//a[contains(@class,"u-ratio--lightbox")]/@href').getall():
            coll['push'](href)
        metadata.art = coll['list']
