from __future__ import annotations

import re
from typing import Any

from parsel import Selector

from phoenixadult.clients.base import Client, LoadedScene, LoadedSearch
from phoenixadult.models.scrape import SceneDetail
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import absolute_first_attr, first_attr, first_text
from phoenixadult.utils.helpers.urls import absolute_url

_READ_LESS_RE = re.compile(r'\s*Read less\s*$', re.IGNORECASE)


class DarkRoomVRClient(Client):
    search_url_xpath = '@href'
    search_rows_xpath = '//a[contains(@class,"video-card__item")]'
    title_xpath = '//h1'
    genres_xpath = '//a[contains(@class,"tags__item")]'

    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/div[contains(@class,"video-card__title")]')

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = first_text(details_page_elements, '//div[@data-id="description" and contains(@class,"hidden")]')
        if not raw:
            return

        metadata.summary = _READ_LESS_RE.sub('', raw).strip() or ''

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_text(details_page_elements, '//div[contains(@class,"video-info__time")]')
        if not date:
            return

        after = date.split(' • ')[-1].strip()

        metadata.release_date = iso_date(after) or None

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            return absolute_first_attr(sel, '(//img[contains(@class,"pornstar-detail__picture")]/@src)[1]', base)

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath('//div[contains(@class,"video-info__text")]//a'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name and href:
                refs.append((actor_name, absolute_url(href, base)))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture, label=scene.site.name)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url((image or '').strip(), scene.site.base_url))
        for href in details_page_elements.xpath('//div[contains(@class,"video-detail__gallery-item")]//a/@href').getall():
            images.push(href)

        metadata.art = images.items
