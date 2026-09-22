from __future__ import annotations

from typing import Any

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene, LoadedSearch
from phoenixadult.models.scrape import SceneDetail, SearchContext
from phoenixadult.utils.helpers.helpers import absolute_url, iso_date
from phoenixadult.utils.helpers.html_helpers import absolute_first_attr, first_attr, first_text
from phoenixadult.utils.processors.title_case import title_case

_CARD_XP = '//div[contains(concat(" ", normalize-space(@class), " "), " item ")]'
_INFO_LI = '//ul[contains(@class,"more-info")]/li'


class ScrewboxClient(Client):
    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        url = search_data.search_url()
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search "{search_data.title}"')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath(_CARD_XP))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/h4//a')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//a/@href)[1]')
        return absolute_url(href, loaded.site.base_url) if href else ''

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '//div[contains(@class,"item-details-right")]//h1')

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_text(details_page_elements, '//p[contains(@class,"shorter")]')

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'Screwbox'

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = ['Screwbox']

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_text(details_page_elements, f'({_INFO_LI})[2]').replace('RELEASE DATE:', '').strip()

        metadata.release_date = (iso_date(date) if date else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            title_case(genre_link.xpath('normalize-space(.)').get() or '') for genre_link in details_page_elements.xpath(f'({_INFO_LI})[3]//a')
        ]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            return absolute_first_attr(sel, '(//img[contains(@class,"model_bio_thumb")]/@src0_1x)[1]', base)

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath(f'({_INFO_LI})[1]//a'):
            actor_name = title_case(first_attr(actor_link, 'normalize-space(.)'))
            href = first_attr(actor_link, '@href')
            if actor_name:
                refs.append((actor_name, absolute_url(href, base) if href else ''))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture, label='actor')

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = first_attr(details_page_elements, '(//div[contains(@class,"fakeplayer")]//img/@src0_1x)[1]')
        if not raw:
            return

        metadata.art = [absolute_url(raw, scene.site.base_url)]
