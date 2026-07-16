from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_attr, first_text


class BAMVisionsClient(Client):
    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        base = search_data.site_info.base_url.rstrip('/')
        url = base + search_data.site_info.search_path.replace('{query}', search_data.encoded)
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search "{search_data.title}"')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath('//div[contains(@class,"category_listing_wrapper_updates")]'))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/h3//a')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//h3//a/@href)[1]')
        if not href:
            return ''

        return absolute_url(href, loaded.site.base_url)

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '//div[contains(@class,"item-info")]//h4//a')

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_text(details_page_elements, '//p[contains(@class,"description")]')

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'BAMVisions'

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = ['BAMVisions']

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        li = first_text(details_page_elements, '//ul[contains(@class,"item-meta")]//li')
        if not li:
            return

        after = li.split('Release Date:')[-1].strip()

        metadata.release_date = iso_date(after, '%B %d, %Y') or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.genres = ['Anal', 'Hardcore']

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        actors: list[ActorResult] = []
        seen: set[str] = set()
        for actor_link in details_page_elements.xpath('//div[contains(@class,"item-info")]//h5//a'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if not actor_name or not href or actor_name in seen:
                continue

            seen.add(actor_name)
            actor_url = absolute_url(href, scene.site.base_url)
            model_page_elements = await self.fetch_and_load(actor_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {actor_name}')
            photo = ''
            if model_page_elements:
                raw = first_attr(model_page_elements['sel'], '(//div[contains(@class,"profile-pic")]//img/@src0_3x)[1]')
                photo = (absolute_url(raw, scene.site.base_url)) if raw else ''

            actors.append(ActorResult(name=actor_name, photo_url=photo))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image, scene.site.base_url))
        for el in details_page_elements.xpath('//img[contains(@class,"update_thumb")]'):
            images['push'](first_attr(el, '@src0_3x'))

        metadata.art = images['list']
