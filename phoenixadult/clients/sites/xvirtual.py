from __future__ import annotations

from typing import Any

from phoenixadult.clients.base import Client, LoadedScene, LoadedSearch
from phoenixadult.models.scrape import SceneDetail
from phoenixadult.utils.helpers.helpers import absolute_url, iso_date, strip_query
from phoenixadult.utils.helpers.html_helpers import first_text, meta_content


class XVirtualClient(Client):
    search_url_xpath = '(.//a/@href)[1]'
    search_rows_xpath = '//div[contains(@class,"episode-list")]/div[contains(@class,"episode")]'
    genres_xpath = '//ul[contains(@class,"tags")]//a'

    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/h2')

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '//div[contains(@class,"title")]//h2')

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_text(details_page_elements, '//div[contains(@class,"description")]//div[contains(@class,"desc-text")]')

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        if not scene.scene_date:
            return

        metadata.release_date = iso_date(scene.scene_date) or scene.scene_date

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.actors = []

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(strip_query(image), scene.site.base_url))
        images.push(meta_content(details_page_elements, 'og:image', 'property'))
        for row in details_page_elements.xpath('//div[contains(@class,"thumbnails")]//img'):
            images.push(row.xpath('@src').get() or '')

        metadata.art = images.items
