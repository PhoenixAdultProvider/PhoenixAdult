from __future__ import annotations

from typing import Any

from parsel import Selector

from app.clients.base import Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_attr
from app.utils.processors.title_case import title_case

STUDIO = 'Teen Mega World'
_SEARCH_PAGES = 2


class TeenMegaWorldClient(Client):
    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        base = search_data.site_info.base_url.rstrip('/')
        sources: list[Any] = []
        for p in range(1, _SEARCH_PAGES + 1):
            url = f'{base}{search_data.site_info.search_path.replace("{query}", search_data.encoded)}&page={p}'
            search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {url}')
            if search_results:
                sources.extend(search_results['sel'].xpath('//div[contains(@class,"thumb") and contains(@class,"thumb-video")]'))

        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return (source.xpath('(.//a[contains(@class,"thumb__title-link")])[1]').xpath('string(.)').get() or '').strip()

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//a[contains(@class,"thumb__title-link")])[1]/@href')
        return absolute_url(href, loaded.site.base_url) if href else ''

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw = (source.xpath('(.//time)[1]').xpath('string(.)').get() or '').strip()
        return (iso_date(raw) if raw else None) or loaded.ctx.search_date

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = (details_page_elements.xpath('(//h1[@id="video-title"])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = (details_page_elements.xpath('(//p[contains(@class,"video-description-text")])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    def _tagline(self, scene: LoadedScene) -> str:
        details_page_elements = scene.require_sel()

        raw = (details_page_elements.xpath('(//a[contains(@class,"video-site-link")])[1]').xpath('string(.)').get() or '').strip()
        return title_case(raw, site_name=scene.site.name) if raw else scene.site.name

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline(scene)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [self._tagline(scene)]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = (details_page_elements.xpath('(//span[@title="Video release date"])[1]').xpath('string(.)').get() or '').strip()
        if date:
            metadata.release_date = iso_date(date)
            return

        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            genre_link.xpath('normalize-space(.)').get() for genre_link in details_page_elements.xpath('//a[contains(@class,"video-tag-link")]')
        ]

        metadata.genres = self.dedup_strings(values) or []

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            raw = first_attr(sel, '(//div[contains(@class,"model-profile-image-wrap")]//img)[1]/@src')
            return absolute_url(raw, base) if raw else ''

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath('//a[contains(@class,"video-actor-link") and contains(@class,"actor__link")]'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name:
                refs.append((actor_name, absolute_url(href, base) if href else ''))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, capture=None) or []

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image, scene.site.base_url))
        for image_url in details_page_elements.xpath('//img[@id="video-cover-image"]/@src').getall():
            images['push'](image_url)

        metadata.art = images['list'] or []
