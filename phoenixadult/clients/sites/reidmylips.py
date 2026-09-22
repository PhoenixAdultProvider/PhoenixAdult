from __future__ import annotations

from typing import Any

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene, LoadedSearch
from phoenixadult.models.scrape import ActorResult, SceneDetail, SearchContext
from phoenixadult.utils.helpers.helpers import absolute_url, iso_date
from phoenixadult.utils.helpers.html_helpers import first_text


class ReidMyLipsClient(Client):
    genres_xpath = '//span[contains(@class,"update_tags")]//a'

    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        base = search_data.site_info.base_url.rstrip('/')
        slug = '-'.join(search_data.title.strip().lower().split())
        scene_url = f'{base}/updates/{slug}.html'
        search_results = await self.fetch_and_load(scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] guess {scene_url}')
        if not search_results:
            return None

        if not first_text(search_results['sel'], '//span[contains(@class,"update_title")]'):
            return None

        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=[search_results['sel']], capture=search_data.capture, extra=scene_url)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, '//span[contains(@class,"update_title")]')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        return str(loaded.extra)

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        return iso_date(first_text(source, '//span[contains(@class,"availdate")]'))

    async def fetch_search_score(self, source: Any, loaded: LoadedSearch) -> float | None:
        return 100

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '//span[contains(@class,"update_title")]')

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_text(details_page_elements, '//span[contains(@class,"latest_update_description")]')

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'ReidMyLips'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_text(details_page_elements, '//span[contains(@class,"availdate")]')

        metadata.release_date = (iso_date(date) if date else None) or scene.scene_date or None

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.actors = [ActorResult(name='Riley Reid')]

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image, scene.site.base_url))
        for image_url in details_page_elements.xpath('//div[contains(@class,"update_image")]//img/@src0_2x').getall():
            images.push((image_url or '').strip())

        metadata.art = images.items
