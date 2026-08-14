from __future__ import annotations

from typing import Any

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from phoenixadult.utils.helpers.helpers import absolute_url, relative_iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text


class CumLouderClient(Client):
    search_url_xpath = '@href'
    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        url = search_data.search_url()
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search "{search_data.title}"')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath('//div[contains(@class,"listado-escenas")]//div[contains(@class,"medida")]/a'))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/h2')

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '//h1') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_text(details_page_elements, '//div[@id="content-more-less"]/p') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'CumLouder'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_text(details_page_elements, '//div[contains(@class,"added")]')

        metadata.release_date = relative_iso_date(date) if date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres = self.dedup_strings(
            [first_attr(genre_link, 'normalize-space(.)') for genre_link in details_page_elements.xpath('//ul[contains(@class,"tags")]/li/a')]
        )
        actor_count = len(details_page_elements.xpath('//a[contains(@class,"pornstar-link")]'))
        if (group := self.group_genre_for(actor_count)) and group not in genres:
            genres.append(group)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        entries = [
            ActorResult(name=actor_link.xpath('normalize-space(.)').get() or '')
            for actor_link in details_page_elements.xpath('//a[contains(@class,"pornstar-link")]')
        ]

        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image, scene.site.base_url))
        for row in details_page_elements.xpath('//div[contains(@class,"box-video-html5")]/video'):
            images['push'](first_attr(row, '@lazy'))

        metadata.art = images['list']
