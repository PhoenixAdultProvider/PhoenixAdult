from __future__ import annotations

from typing import Any
from urllib.parse import quote

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from app.utils.helpers.helpers import absolute_url
from app.utils.helpers.html_helpers import first_attr, first_text

# `div.update` cards must match the class token exactly (updateTitle, updateDescription, etc. all contain "update").
_UPDATE_CARD_XP = '//div[contains(concat(" ", normalize-space(@class), " "), " update ")]'


class BoundHoneysClient(Client):
    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        base = search_data.site_info.base_url.rstrip('/')
        url = base + search_data.site_info.search_path.replace('{query}', quote(search_data.title, safe=''))
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search "{search_data.title}"')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath(_UPDATE_CARD_XP))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/div[contains(@class,"updateTitle")]')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//div[contains(@class,"updateTitle")]//a/@href)[1]')
        if not href:
            return ''

        return absolute_url(href, loaded.site.base_url)

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '//div[contains(@class,"updateVideoTitle")]') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_text(details_page_elements, '//div[contains(@class,"updateDescription")]//b') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'Bound Honeys'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def _collect_actors(self, scene: LoadedScene) -> list[ActorResult]:
        details_page_elements = scene.require_sel()

        actors: list[ActorResult] = []
        seen: set[str] = set()
        for actor_link in details_page_elements.xpath('//div[contains(@class,"updateModelsList")]//a'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if not actor_name or not href or actor_name in seen:
                continue

            seen.add(actor_name)
            actor_url = absolute_url(href, scene.site.base_url)
            model_page_elements = await self.fetch_and_load(actor_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {actor_name}')
            photo = ''
            if model_page_elements:
                raw = first_attr(model_page_elements['sel'], '(//div[contains(@class,"modelDetailPhoto")]//img/@src)[1]')
                photo = absolute_url(raw, scene.site.base_url) if raw else ''

            actors.append(ActorResult(name=actor_name, photo_url=photo))

        return actors

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
            images['push'](href)

        metadata.art = images['list']
