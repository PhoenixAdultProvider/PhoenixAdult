from __future__ import annotations

import re
from typing import Any

from parsel import Selector

from phoenixadult.clients.base import Client, LoadedScene, LoadedSearch
from phoenixadult.models.scrape import SceneDetail
from phoenixadult.utils.helpers.helpers import absolute_url, iso_date
from phoenixadult.utils.helpers.html_helpers import absolute_first_attr, first_attr, first_text

_TITLE_LINK_XP = '(.//a[contains(@class,"update_title")])[2]'
_ADDED_PREFIX = re.compile(r'^Added:\s*', re.IGNORECASE)


class DesperateAmateursClient(Client):
    search_rows_xpath = '//div[@align="left"]'
    title_xpath = '//div[contains(@class,"title_bar")]'
    summary_xpath = '//div[contains(@class,"gallery_description")]'
    genres_xpath = '//a[starts-with(@href,"category")]'

    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, _TITLE_LINK_XP)

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = (source.xpath(f'({_TITLE_LINK_XP}/@href)[1]').get() or '').strip()
        if not href:
            return ''

        return absolute_url(href, loaded.site.base_url)

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw = first_text(source, './/span[contains(@class,"date")]')
        stripped = _ADDED_PREFIX.sub('', raw).strip()
        return iso_date(stripped) if stripped else None

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'Desperate Amateurs'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_text(details_page_elements, '//td[contains(@class,"date")]')
        if not date:
            return

        after = date.split('Added:')[-1].strip()

        metadata.release_date = iso_date(after) if after else None

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            return absolute_first_attr(sel, '(//img[contains(@class,"thumbs")]/@src)[1]', base)

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath('//a[starts-with(@href,"sets")]'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name and href:
                refs.append((actor_name, absolute_url(href, base)))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image, scene.site.base_url))
        for row in details_page_elements.xpath('//div[contains(@class,"gal")]//img'):
            images.push(first_attr(row, '@src'))

        metadata.art = images.items
