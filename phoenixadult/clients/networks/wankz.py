from __future__ import annotations

from typing import Any

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from phoenixadult.utils.helpers.helpers import absolute_url, iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr
from phoenixadult.utils.processors.similarity import compare_string

STUDIO = 'Wankz'


class WankzClient(Client):
    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        base = search_data.site_info.base_url.rstrip('/')
        url = base + search_data.site_info.search_path.replace('{query}', search_data.encoded)
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {url}')
        if not search_results:
            return None

        sources: list[Any] = list(search_results['sel'].xpath('//div[contains(@class,"scene")]'))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return (source.xpath('(.//div[contains(@class,"title-wrapper")]//a[contains(@class,"title")])[1]').xpath('string(.)').get() or '').strip()

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//a)[1]/@href')
        return absolute_url(href, loaded.site.base_url) if href else ''

    async def fetch_search_score(self, source: Any, loaded: LoadedSearch) -> float | None:
        title = (source.xpath('(.//div[contains(@class,"title-wrapper")]//a[contains(@class,"title")])[1]').xpath('string(.)').get() or '').strip()
        sub_site = (source.xpath('(.//div[contains(@class,"series-container")]//a[contains(@class,"sitename")])[1]').xpath('string(.)').get() or '').strip()
        site_dist = compare_string(sub_site.lower(), loaded.site.name.lower()).levenshtein
        title_dist = compare_string(loaded.ctx.title.lower(), title.lower()).levenshtein
        return 80 - (site_dist * 8) // 10 + (20 - (title_dist * 2) // 10)

    async def fetch_search_subsite(self, source: Any, loaded: LoadedSearch) -> str | None:
        return (source.xpath('(.//div[contains(@class,"series-container")]//a[contains(@class,"sitename")])[1]').xpath('string(.)').get() or '').strip() or None

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = (details_page_elements.xpath('(//div[contains(@class,"title")]//h1)[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = (details_page_elements.xpath('(//div[contains(@class,"description")]//p)[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [STUDIO]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = (details_page_elements.xpath('(//div[contains(@class,"views")]//span)[1]').xpath('string(.)').get() or '').replace('Added', '').strip()
        if date:
            metadata.release_date = iso_date(date)
            return

        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            genre_link.xpath('normalize-space(.)').get() for genre_link in details_page_elements.xpath('//a[contains(@class,"cat")] | //p[@style]//a')
        ]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        entries = [
            ActorResult(
                name=(actor_link.xpath('(.//span)[1]').xpath('string(.)').get() or '').strip(),
                photo_url=first_attr(actor_link, '(.//img)[1]/@src'),
            )
            for actor_link in details_page_elements.xpath('//div[contains(@class,"actors")]//a[contains(@class,"model")]')
        ]

        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image, scene.site.base_url))
        for image_url in details_page_elements.xpath('//a[contains(@class,"noplayer")]//img/@src').getall():
            images['push'](image_url)

        metadata.art = images['list']
