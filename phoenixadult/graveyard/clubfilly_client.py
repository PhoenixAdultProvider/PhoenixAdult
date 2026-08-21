from __future__ import annotations

import re
from typing import Any

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from phoenixadult.utils.helpers.helpers import absolute_url, iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text

_TITLE_XP = '//div[contains(@class,"fltWrap")]/h1/span'
_DESC_PREFIX = re.compile(r'^Description:\s*')
_DATE_PREFIX = re.compile(r'^Release Date\s*:\s*')
_STARRING_PREFIX = re.compile(r'^Starring:\s*')


class ClubFillyClient(Client):
    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        scene_url = search_data.search_url(search_data.title.strip())
        direct_page_elements = await self.fetch_and_load(
            scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] directScene {scene_url}'
        )
        if not direct_page_elements:
            return None

        if not first_text(direct_page_elements['sel'], _TITLE_XP):
            return None

        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=[direct_page_elements['sel']], capture=search_data.capture, extra=scene_url)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, _TITLE_XP)

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        return str(loaded.extra)

    async def fetch_search_score(self, source: Any, loaded: LoadedSearch) -> float | None:
        return 100

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _collect_actors(self, scene: LoadedScene) -> list[ActorResult]:
        details_page_elements = scene.require_sel()

        raw = first_text(details_page_elements, '//p[contains(@class,"starring")]')
        text = _STARRING_PREFIX.sub('', raw).strip()
        if not text:
            return []

        names = [n.strip() for n in text.split(',') if n.strip()]
        return [ActorResult(name=actor_name) for actor_name in names]

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, _TITLE_XP) or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = first_text(details_page_elements, '//p[contains(@class,"description")]')
        if not raw:
            return

        metadata.summary = _DESC_PREFIX.sub('', raw).strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'ClubFilly'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_text(details_page_elements, '//div[contains(@class,"fltRight")]')
        date_text = _DATE_PREFIX.sub('', date).strip()

        metadata.release_date = iso_date(date_text, '%Y-%m-%d') or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        genres = ['Lesbian']
        n = len(self._collect_actors(scene))
        if group := self.group_genre_for(n):
            genres.append(group)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.actors = self._collect_actors(scene)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image, scene.site.base_url))
        for row in details_page_elements.xpath('//ul[@id="lstSceneFocus"]/li/img'):
            images.push(first_attr(row, '@src'))

        metadata.art = images.items
