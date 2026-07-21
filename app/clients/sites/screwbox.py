from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_attr, first_text
from app.utils.processors.title_case import title_case

_CARD_XP = '//div[contains(concat(" ", normalize-space(@class), " "), " item ")]'
_INFO_LI = '//ul[contains(@class,"more-info")]/li'


class ScrewboxClient(Client):
    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        base = search_data.site_info.base_url.rstrip('/')
        url = base + search_data.site_info.search_path.replace('{query}', search_data.encoded)
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

        actors: list[ActorResult] = []
        seen: set[str] = set()
        for actor_link in details_page_elements.xpath(f'({_INFO_LI})[1]//a'):
            actor_name = title_case(first_attr(actor_link, 'normalize-space(.)'))
            if not actor_name or actor_name in seen:
                continue

            seen.add(actor_name)
            photo = ''
            href = first_attr(actor_link, '@href')
            if href:
                model_page_elements = await self.fetch_and_load(absolute_url(href, scene.site.base_url), FetchCtx(capture=scene.capture), f'GET {href} (actor)')
                raw = first_attr(model_page_elements['sel'], '(//img[contains(@class,"model_bio_thumb")]/@src0_1x)[1]') if model_page_elements else ''
                photo = (absolute_url(raw, scene.site.base_url)) if raw else ''

            actors.append(ActorResult(name=actor_name, photo_url=photo))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = first_attr(details_page_elements, '(//div[contains(@class,"fakeplayer")]//img/@src0_1x)[1]')
        if not raw:
            return

        metadata.art = [absolute_url(raw, scene.site.base_url)]
