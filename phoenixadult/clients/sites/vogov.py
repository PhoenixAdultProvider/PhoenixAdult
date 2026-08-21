from __future__ import annotations

from typing import Any

from parsel import Selector

from phoenixadult.clients.base import ActorResult, Client, LoadedScene, LoadedSearch, SceneDetail
from phoenixadult.utils.helpers.helpers import absolute_url, iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text

_HARDCODED_DIRECTOR = 'Markus Dupree'


class VogoVClient(Client):
    search_url_xpath = '(.//a[contains(@class,"video-post-main")]/@href)[1]'
    search_rows_xpath = '//div[contains(@class,"video-post-content")]'
    title_xpath = '//div[contains(@class,"video-page-header")]//h1'
    summary_xpath = '//div[contains(@class,"info-video-description")]//p'
    genres_xpath = '//div[contains(@class,"info-video-category")]//a'

    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_attr(source, '(.//a[contains(@class,"video-post-main")]//img/@alt)[1]')

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw = first_text(source, './/span[contains(@class,"video-data") and contains(@class,"float-right")]//em')
        return iso_date(raw) if raw else None

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_text(details_page_elements, '//ul[contains(@class,"list-unstyled") and contains(@class,"info-video-details")]//li[1]//span[1]')
        if date:
            parsed = iso_date(date)
            if parsed:
                metadata.release_date = parsed
                return

        if scene.scene_date:
            metadata.release_date = iso_date(scene.scene_date) or scene.scene_date

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            return first_attr(sel, '(//div[contains(@class,"m-images")]//img/@src)[1]')

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath('//div[contains(@class,"info-video-models")]//a'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name:
                refs.append((actor_name, absolute_url(href, base) if href else ''))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture, label=scene.site.name)

    async def fetch_directors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.directors = [ActorResult(name=_HARDCODED_DIRECTOR)]

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        images = self.image_collector(lambda image: absolute_url((image or '').strip(), base))
        for href in details_page_elements.xpath('//div[contains(@class,"swiper-wrapper")]//figure//a/@href').getall():
            images.push(href)

        metadata.art = images.items
