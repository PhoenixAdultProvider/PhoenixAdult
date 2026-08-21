from __future__ import annotations

from typing import Any

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from phoenixadult.utils.helpers.helpers import absolute_url, iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text

_CARD_XP = '//li[contains(concat(" ", normalize-space(@class), " "), " thumb ")]'
_MODELS_XP = '//ul[contains(.,"Models:")]//li//a'


class FirstAnalQuestClient(Client):
    search_url_xpath = '(.//a[contains(@class,"thumb-img")]/@href)[1]'
    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        url = search_data.search_url()
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search "{search_data.title}"')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath(_CARD_XP))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/span[contains(@class,"thumb-title")]')

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw = first_text(source, './/span[contains(@class,"thumb-added")]')
        return iso_date(raw) if raw else None

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        xp = '//div[contains(@class,"container") and contains(@class,"content")]//div[contains(@class,"page-header")]//span[contains(@class,"title")]'

        metadata.title = first_text(details_page_elements, xp) or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_text(details_page_elements, '//div[contains(@class,"text-desc")]') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'Pioneer'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres = self.dedup_strings(
            [
                first_attr(genre_link, 'normalize-space(.)')
                for genre_link in details_page_elements.xpath('//div[contains(@class,"media-body")]//ul[contains(.,"Categories")]//a')
            ]
        )
        if 'porn-movie' not in scene.url:
            count = len(details_page_elements.xpath(_MODELS_XP))
            if (group := self.group_genre_for(count)) and group not in genres:
                genres.append(group)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            raw = first_attr(sel, '(//div[contains(@class,"model-box")]//img/@src)[1]')
            return absolute_url(raw, base) if raw else ''

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath(_MODELS_XP):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name and href:
                refs.append((actor_name, absolute_url(href, base)))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture, label=scene.site.name)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url((image or '').strip(), scene.site.base_url))
        for image_url in details_page_elements.xpath('//img[contains(@class,"player-preview")]/@src').getall():
            images.push(image_url)

        for image_url in details_page_elements.xpath('//a[contains(@class,"fancybox") and contains(@class,"img-album")]/@href').getall():
            images.push(image_url)

        for image_url in details_page_elements.xpath('//a[@data-fancybox-group="gallery"]/@href').getall():
            images.push(image_url)

        metadata.art = images.items
