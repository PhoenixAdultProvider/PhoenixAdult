from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_attr

STUDIO = 'Porndoe Premium'
_TITLE_SEL = './/div[@class="-g-vc-item-title"]//a'


class PorndoePremiumClient(Client):
    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        base = search_data.site_info.base_url.rstrip('/')
        url = base + search_data.site_info.search_path.replace('{query}', search_data.encoded)
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {url}')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath('//div[contains(@class,"main-content")]//div[@class="-g-vc-grid"]'))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return (source.xpath(f'({_TITLE_SEL})[1]/@title').get() or '').strip()

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = (source.xpath(f'({_TITLE_SEL})[1]/@href').get() or '').strip()
        return absolute_url(href, loaded.site.base_url) if href else ''

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        return iso_date((source.xpath('(.//div[@class="-g-vc-item-date"])[1]').xpath('string(.)').get() or '').strip())

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = (details_page_elements.xpath('(//h1[@class="-mvd-heading"])[1]').xpath('string(.)').get() or '').strip()

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = (details_page_elements.xpath('(//div[@class="-mvd-description"])[1]').xpath('string(.)').get() or '').strip()

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    def _first_actor(self, scene: LoadedScene) -> str:
        details_page_elements = scene.require_sel()

        return (details_page_elements.xpath('(//div[@class="-mvd-grid-actors"]//span/a)[1]').xpath('string(.)').get() or '').strip()

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._first_actor(scene) or None

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        tag = self._first_actor(scene)

        metadata.collections = [tag] if tag else None

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        stats = (details_page_elements.xpath('(//div[@class="-mvd-grid-stats"])[1]').xpath('string(.)').get() or '').strip()
        date = stats.split('•')[-1].strip() if stats else ''

        metadata.release_date = (iso_date(date) if date else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            genre_link.xpath('normalize-space(.)').get() for genre_link in details_page_elements.xpath('//span[@class="-mvd-list-item"]/a')
        ]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for actor_link in details_page_elements.xpath('//div[@class="-mvd-grid-actors"]//span/a[@title]'):
            href = first_attr(actor_link, '@href')
            if not href:
                continue

            model_page_elements = await self.fetch_and_load(absolute_url(href, base), None, f'GET {href} (actor)')
            if not model_page_elements:
                continue

            actor_name = (model_page_elements['sel'].xpath('(//div[@class="-aph-heading"]//h1)[1]').xpath('string(.)').get() or '').strip()
            if not actor_name or actor_name in seen:
                continue

            seen.add(actor_name)
            raw = first_attr(model_page_elements['sel'], '(//div[@class="-api-poster-item"]//img)[1]/@src')
            photo = (absolute_url(raw, base)) if raw else ''
            actors.append(ActorResult(name=actor_name, photo_url=photo))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image, scene.site.base_url))
        xpaths = (
            '//picture[@class="-vcc-picture"]//img/@src',
            '//div[@class="swiper-wrapper"]/div/a/div/@data-bg',
        )
        for xpath in xpaths:
            for image_url in details_page_elements.xpath(xpath).getall():
                images['push'](image_url.strip())

        metadata.art = images['list']
