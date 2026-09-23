from __future__ import annotations

from typing import Any

from parsel import Selector

from phoenixadult.clients.base import Client, LoadedScene, LoadedSearch
from phoenixadult.models.scrape import SceneDetail, SearchContext
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import absolute_first_attr, first_attr, first_text
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.text import slugify
from phoenixadult.utils.helpers.urls import absolute_url, css_bg_image

_DATE_XP = (
    '//span[contains(@class,"date-display-single")]'
    ' | //span[contains(@class,"u-inline-block") and contains(@class,"u-mr--nine")]'
    ' | //div[contains(@class,"video-meta-date")]'
    ' | //div[contains(@class,"date")]'
)


class LustRealityClient(Client):
    candidate_include = ('/scene/',)
    title_xpath = '//h1'
    summary_xpath = '//div[contains(@class,"u-mb--six")]'
    genres_xpath = '//a[contains(@href,"/list/category/")]'

    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def candidate_urls(self, search_data: SearchContext) -> list[str]:
        base = search_data.site_info.base_url.rstrip('/')
        return [f'{base}{search_data.site_info.search_path}{slugify(search_data.title)}']

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        return iso_date(first_text(source.sel, _DATE_XP))

    def search_cur_id(self, scene_url: str, date: str | None, loaded: LoadedSearch) -> str:
        return pack_cur_id([p for p in (scene_url, date or loaded.ctx.search_date) if p])

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.release_date = iso_date(first_text(details_page_elements, _DATE_XP)) or scene.scene_date or None

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            return absolute_first_attr(sel, '(//div[contains(@class,"u-ratio--model-poster")]//img/@data-src)[1]', base)

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath('//a[contains(@href,"/pornstars/model/")]'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            if not actor_name:
                continue

            href = first_attr(actor_link, '@href')
            refs.append((actor_name, absolute_url(href, base) if href else ''))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image.strip(), scene.site.base_url))
        for row in details_page_elements.xpath('//div[contains(@class,"splash-screen")]'):
            images.push(css_bg_image(row.xpath('@style').get()))

        for href in details_page_elements.xpath('//a[contains(@class,"u-ratio--lightbox")]/@href').getall():
            images.push(href)

        metadata.art = images.items
