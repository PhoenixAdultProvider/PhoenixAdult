from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from app.utils.helpers.helpers import absolute_url, append_unique, iso_date
from app.utils.helpers.html_helpers import first_attr, first_text

_ACTOR_XP = '//div/strong[normalize-space(text())="Starring"]/following-sibling::span//a[contains(@class,"tiny-link")]'


class XSinsVRClient(Client):
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

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//a[contains(@class,"tn-video-media")]/@href)[1]')
        if not href:
            return ''

        return absolute_url(href, loaded.site.base_url)

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

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

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

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            genre_link.xpath('normalize-space(.)').get() for genre_link in details_page_elements.xpath('//div[contains(@class,"tags-item")]')
        ]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for actor_link in details_page_elements.xpath(_ACTOR_XP):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if not actor_name or actor_name in seen:
                continue

            seen.add(actor_name)
            photo = ''
            if href:
                url = absolute_url(href, base)
                model_page_elements = await self.fetch_and_load(url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {actor_name}')
                if model_page_elements:
                    raw = first_attr(model_page_elements['sel'], '(//div[contains(@class,"model-header__photo")]//img/@src)[1]')
                    if raw:
                        photo = absolute_url(raw, base)

            actors.append(ActorResult(name=actor_name, photo_url=photo))

        metadata.actors = actors

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
