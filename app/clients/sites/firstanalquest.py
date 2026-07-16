from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_attr, first_text

_CARD_XP = '//li[contains(concat(" ", normalize-space(@class), " "), " thumb ")]'
_MODELS_XP = '//ul[contains(.,"Models:")]//li//a'


class FirstAnalQuestClient(Client):
    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        base = search_data.site_info.base_url.rstrip('/')
        url = base + search_data.site_info.search_path.replace('{query}', search_data.encoded)
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search "{search_data.title}"')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath(_CARD_XP))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/span[contains(@class,"thumb-title")]')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//a[contains(@class,"thumb-img")]/@href)[1]')
        if not href:
            return ''

        return absolute_url(href, loaded.site.base_url)

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw = first_text(source, './/span[contains(@class,"thumb-added")]')
        return iso_date(raw) if raw else None

    # ── Detail field hooks ────────────────────────────────────────────────────

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

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = scene.scene_date or None

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

        actors: list[ActorResult] = []
        seen: set[str] = set()
        for actor_link in details_page_elements.xpath(_MODELS_XP):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if not actor_name or not href or actor_name in seen:
                continue

            seen.add(actor_name)
            actor_url = absolute_url(href, scene.site.base_url)
            model_page_elements = await self.fetch_and_load(actor_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {actor_name}')
            photo = ''
            if model_page_elements:
                raw = first_attr(model_page_elements['sel'], '(//div[contains(@class,"model-box")]//img/@src)[1]')
                photo = (absolute_url(raw, scene.site.base_url)) if raw else ''

            actors.append(ActorResult(name=actor_name, photo_url=photo))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url((image or '').strip(), scene.site.base_url))
        for image_url in details_page_elements.xpath('//img[contains(@class,"player-preview")]/@src').getall():
            images['push'](image_url)

        for image_url in details_page_elements.xpath('//a[contains(@class,"fancybox") and contains(@class,"img-album")]/@href').getall():
            images['push'](image_url)

        for image_url in details_page_elements.xpath('//a[@data-fancybox-group="gallery"]/@href').getall():
            images['push'](image_url)

        metadata.art = images['list']
