from __future__ import annotations

from typing import Any
from urllib.parse import quote

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene, LoadedSearch
from phoenixadult.models.scrape import ActorResult, SceneDetail, SearchContext
from phoenixadult.utils.helpers.html_helpers import absolute_first_attr, first_attr, first_text
from phoenixadult.utils.helpers.urls import absolute_url

_UPDATE_CARD_XP = '//div[contains(concat(" ", normalize-space(@class), " "), " update ")]'


class BoundHoneysClient(Client):
    search_url_xpath = '(.//div[contains(@class,"updateTitle")]//a/@href)[1]'
    title_xpath = '//div[contains(@class,"updateVideoTitle")]'
    summary_xpath = '//div[contains(@class,"updateDescription")]//b'

    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        url = search_data.search_url(quote(search_data.title, safe=''))
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search "{search_data.title}"')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath(_UPDATE_CARD_XP))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/div[contains(@class,"updateTitle")]')

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    async def _collect_actors(self, scene: LoadedScene) -> list[ActorResult]:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            return absolute_first_attr(sel, '(//div[contains(@class,"modelDetailPhoto")]//img/@src)[1]', base)

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath('//div[contains(@class,"updateModelsList")]//a'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name and href:
                refs.append((actor_name, absolute_url(href, base)))

        return await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture, label='actor')

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres = self.dedup_strings(
            [first_attr(genre_link, 'normalize-space(.)') for genre_link in details_page_elements.xpath('//div[contains(@class,"updateCategoriesList")]//a')]
        )
        n = len(await self._collect_actors(scene))
        if group := self.group_genre_for(n):
            genres.append(group)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.actors = await self._collect_actors(scene)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url((image or '').strip(), scene.site.base_url))
        for href in details_page_elements.xpath('//link[@rel="preload"]/@href').getall():
            images.push(href)

        metadata.art = images.items
