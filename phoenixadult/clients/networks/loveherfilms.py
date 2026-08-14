from __future__ import annotations

from typing import Any

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from phoenixadult.utils.helpers.helpers import absolute_url, iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr

STUDIO = 'LoveHerFilms'
_DATE_FMT = '%B %d, %Y'


class LoveHerFilmsClient(Client):
    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        url = search_data.search_url()
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {url}')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath('//div[contains(@class,"item-video-overlay")]'))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_attr(source, '(.//a)[1]/@title')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//a)[1]/@href')
        return absolute_url(href, loaded.site.base_url) if href else ''

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw = (source.xpath('(.//p[contains(@class,"video-date")])[1]').xpath('string(.)').get() or '').strip()
        return (iso_date(raw) if raw else None) or loaded.ctx.search_date

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = (details_page_elements.xpath('(//div[contains(@class,"main-info-left")]/h1)[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = (details_page_elements.xpath('(//p[contains(@class,"description")])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = (details_page_elements.xpath('(//div[contains(@class,"date")])[1]').xpath('string(.)').get() or '').strip()
        if date:
            metadata.release_date = iso_date(date, _DATE_FMT)
            return

        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres = self.dedup_strings(
            [first_attr(genre_link, 'normalize-space(.)') for genre_link in details_page_elements.xpath('//div[contains(@class,"video-tags")]/a')]
        )
        if 'Foot Sex' not in genres:
            genres.append('Foot Sex')

        cast = len(details_page_elements.xpath('//div[contains(@class,"featured")]/a'))
        if (group := self.group_genre_for(cast)) and group not in genres:
            genres.append(group)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            raw = first_attr(sel, '(//div[contains(@class,"picture")]//img)[1]/@src0_3x')
            return absolute_url(raw, base) if raw else ''

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath('//div[contains(@class,"featured")]/a'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name:
                refs.append((actor_name, absolute_url(href, base) if href else ''))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, capture=None)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        images = self.image_collector(lambda image: absolute_url(image, base))
        xpaths = (
            '//meta[@property="og:image"]/@content',
            '//div[contains(@class,"photos")]//a//img/@src',
        )
        for xpath in xpaths:
            for image_url in details_page_elements.xpath(xpath).getall():
                images['push'](image_url)

        metadata.art = images['list']
