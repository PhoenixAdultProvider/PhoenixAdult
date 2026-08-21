from __future__ import annotations

from typing import Any

from phoenixadult.clients.base import Client, LoadedScene, LoadedSearch, SceneDetail
from phoenixadult.utils.helpers.helpers import absolute_url, relative_iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text


class CumLouderClient(Client):
    search_url_xpath = '@href'
    search_rows_xpath = '//div[contains(@class,"listado-escenas")]//div[contains(@class,"medida")]/a'
    title_xpath = '//h1'
    summary_xpath = '//div[@id="content-more-less"]/p'
    actors_xpath = '//a[contains(@class,"pornstar-link")]'

    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/h2')

    # ── Update Field Hooks ────────────────────────────────────────────────────

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

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image, scene.site.base_url))
        for row in details_page_elements.xpath('//div[contains(@class,"box-video-html5")]/video'):
            images.push(first_attr(row, '@lazy'))

        metadata.art = images.items
