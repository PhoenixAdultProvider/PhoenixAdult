from __future__ import annotations

from typing import Any

from parsel import Selector

from phoenixadult.clients.base import Client, LoadedScene, LoadedSearch
from phoenixadult.models.scrape import SceneDetail, SearchContext
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text, meta_content
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.urls import absolute_url, to_https


def _title_or_text(node: Any) -> str:
    return (node.xpath('@title').get() or node.xpath('normalize-space(.)').get() or '').strip()


class VRLatinaClient(Client):
    candidate_include = ('/video/',)
    title_xpath = '//h2'
    summary_xpath = '//div[contains(@class,"content-desc")]'

    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def candidate_urls(self, search_data: SearchContext) -> list[str]:
        slug = search_data.title.replace(' ', '-').lower()
        return [f'{search_data.site_info.base_url.rstrip("/")}{search_data.site_info.search_path}{slug}.html'] if slug else []

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return meta_content(source.sel, 'og:title')

    def search_cur_id(self, scene_url: str, date: str | None, loaded: LoadedSearch) -> str:
        return pack_cur_id([scene_url, loaded.ctx.search_date or ''])

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_text(
            details_page_elements, '//div[contains(@class,"content-base-info")]//div[contains(@class,"info-elem") and contains(@class,"-length")]//span'
        )
        if date:
            parsed = iso_date(date, '%b %d, %Y') or iso_date(date)
            if parsed:
                metadata.release_date = parsed
                return

        if scene.scene_date:
            metadata.release_date = iso_date(scene.scene_date) or scene.scene_date

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            _title_or_text(genre_link) for genre_link in details_page_elements.xpath('//div[contains(@class,"content-links") and contains(@class,"-tags")]//a')
        ]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            return first_attr(sel, '(//div[contains(@class,"model-avatar")]//img/@src)[1]')

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath('//div[contains(@class,"content-links") and contains(@class,"-models")]//a'):
            actor_name = _title_or_text(actor_link)
            href = first_attr(actor_link, '@href')
            if actor_name:
                refs.append((actor_name, absolute_url(href, base) if href else ''))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture, label=scene.site.name)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: to_https((image or '').strip()))
        for href in details_page_elements.xpath('//a[contains(@class,"video-gallery-item")]/@href').getall():
            images.push(href)

        images.push(meta_content(details_page_elements, 'og:image', 'property'))

        metadata.art = images.items
