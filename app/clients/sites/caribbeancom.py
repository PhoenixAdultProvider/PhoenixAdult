from __future__ import annotations

import re
from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from app.utils.helpers.helpers import absolute_url
from app.utils.helpers.html_helpers import first_attr, first_text

_UPLOAD_DATE_RE = re.compile(r'(\d{4})/(\d{2})/(\d{2})')


class CaribbeancomClient(Client):
    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        base = search_data.site_info.base_url.rstrip('/')
        scene_id = (search_data.full_title or search_data.title).replace(' ', '-')
        scene_url = base + search_data.site_info.search_path.replace('{query}', scene_id)
        direct_page_elements = await self.fetch_and_load(
            scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] directScene {scene_url}'
        )
        if not direct_page_elements:
            return None

        if not first_text(direct_page_elements['sel'], '//title'):
            return None

        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=[direct_page_elements['sel']], capture=search_data.capture, extra=scene_url)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, '//title')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        return str(loaded.extra)

    async def fetch_search_score(self, source: Any, loaded: LoadedSearch) -> float | None:
        return 100

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '//title') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'caribbeancom'

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = ['caribbeancom']

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_text(details_page_elements, '//span[@itemprop="uploadDate"]')
        if not date:
            return

        m = _UPLOAD_DATE_RE.search(date)

        metadata.release_date = f'{m.group(1)}-{m.group(2)}-{m.group(3)}' if m else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [genre_link.xpath('normalize-space(.)').get() for genre_link in details_page_elements.xpath('//a[@itemprop="genre"]')]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        entries: list[ActorResult] = []
        for actor_link in details_page_elements.xpath('//a[@itemprop="actor"]'):
            text = first_text(actor_link, './/span[@itemprop="name"]')
            for actor_name in (n.strip() for n in text.split(',')):
                if actor_name:
                    entries.append(ActorResult(name=actor_name))

        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images: list[str] = []
        constructed = scene.url.replace('/eng', '').replace('index.html', 'images/poster_en.jpg')
        if constructed != scene.url:
            images.append(constructed)

        for el in details_page_elements.xpath('//img[contains(@class,"gallery-image")]'):
            src = first_attr(el, '@src')
            if not src:
                continue

            abs_url = absolute_url(src, scene.site.base_url)
            if abs_url not in images:
                images.append(abs_url)

        metadata.art = images
