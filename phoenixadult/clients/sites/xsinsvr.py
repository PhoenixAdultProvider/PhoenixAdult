from __future__ import annotations

from typing import Any

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene, LoadedSearch
from phoenixadult.models.scrape import SceneDetail, SearchContext
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import absolute_first_attr, first_attr, first_text
from phoenixadult.utils.helpers.urls import absolute_url, append_unique

_ACTOR_XP = '//div/strong[normalize-space(text())="Starring"]/following-sibling::span//a[contains(@class,"tiny-link")]'


class XSinsVRClient(Client):
    search_url_xpath = '(.//a[contains(@class,"tn-video-media")]/@href)[1]'
    genres_xpath = '//div[contains(@class,"tags-item")]'

    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        base = search_data.site_info.base_url.rstrip('/')
        url = f'{base}{search_data.site_info.search_path}{search_data.title}'
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search "{search_data.title}"')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath('//div[contains(@class,"tn-video") and contains(@class,"tn-video--horizontal")]'))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/a[contains(@class,"tn-video-name")]')

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = first_text(details_page_elements, '//title')

        metadata.title = (raw.split('•')[0].strip() if raw else '') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        parts = [p.xpath('string(.)').get() or '' for p in details_page_elements.xpath('//li/div[contains(@class,"small")]//p')]
        joined = ''.join(parts).strip()

        metadata.summary = joined or ''

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_text(details_page_elements, '//span//time')
        if date:
            parsed = iso_date(date, '%b %d, %Y') or iso_date(date)
            if parsed:
                metadata.release_date = parsed
                return

        if scene.scene_date:
            metadata.release_date = iso_date(scene.scene_date) or scene.scene_date

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            return absolute_first_attr(sel, '(//div[contains(@class,"model-header__photo")]//img/@src)[1]', base)

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath(_ACTOR_XP):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name:
                refs.append((actor_name, absolute_url(href, base) if href else ''))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture, label=scene.site.name)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        images: list[str] = []

        def push(raw: str) -> None:
            append_unique(images, raw, base)

        for src in details_page_elements.xpath('//div[contains(@class,"tn-photo__container")]//div//a//div//img/@src').getall():
            if (src or '').startswith('http'):
                push(src.replace('sceneGallerySmall', 'sceneGallery'))

        for poster in details_page_elements.xpath('//dl8-video/@poster').getall():
            push(poster)

        metadata.art = images
