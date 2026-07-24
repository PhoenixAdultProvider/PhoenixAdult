from __future__ import annotations

import re
from urllib.parse import urlsplit

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.searchengines import SearchOptions, web_search

_DESCRIPTION_RE = re.compile(r'description:\s*', re.IGNORECASE)
_RELEASED_XP = '//div[contains(@class,"released2") and contains(@class,"trailerStarr")]'
_CAST_XP = '//div[contains(@class,"trailerMInfo")]//span[contains(@class,"tour_update_models")]/a'


def _date_of(raw: str) -> str | None:
    seg = raw.split(',')[0].strip()
    return iso_date(seg) if seg else None


class HotwifeXXXClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        host = urlsplit(search_data.site_info.base_url).hostname or ''
        if not host:
            return

        try:
            found = await web_search(SearchOptions(query=search_data.title, site=host, num=10))
        except Exception as err:  # noqa: BLE001 - search failure is non-fatal
            logger.warn(search_data.site_info.name, f'webSearch threw: {err}')
            return

        seen: set[str] = set()
        candidates: list[str] = []
        for u in found:
            if '/updates/' in u and '/tour_hwxxx/' in u and u not in seen:
                seen.add(u)
                candidates.append(u)

        for scene_url in candidates:
            search_results = await self.fetch_and_load(scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] {scene_url}')
            if not search_results:
                continue

            title = first_text(search_results['sel'], '//div[contains(@class,"trailerInfo")]//h2')
            if not title:
                continue

            date = _date_of(first_text(search_results['sel'], _RELEASED_XP))

            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    display_date=date,
                    search_date=search_data.search_date,
                )
            )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '//div[contains(@class,"trailerInfo")]//h2') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = first_text(details_page_elements, '//div[contains(@class,"dvdDescription")]//p')

        metadata.summary = _DESCRIPTION_RE.sub('', raw, count=1).strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'HotwifeXXX'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.release_date = _date_of(first_text(details_page_elements, _RELEASED_XP)) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        count = len(details_page_elements.xpath(_CAST_XP))
        if group := self.group_genre_for(count):
            metadata.genres = [group]

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        actors: list[ActorResult] = []
        for actor_link in details_page_elements.xpath(_CAST_XP):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            if not actor_name:
                continue

            photo = ''
            href = first_attr(actor_link, '@href')
            if href:
                actor_url = absolute_url(href, scene.site.base_url)
                model_page_elements = await self.fetch_and_load(actor_url, FetchCtx(capture=scene.capture), f'GET {actor_url} (actor)')
                raw = first_attr(model_page_elements['sel'], '(//div[contains(@class,"modelBioPic")]//img/@src0_3x)[1]') if model_page_elements else ''
                photo = (absolute_url(raw, scene.site.base_url)) if raw else ''

            actors.append(ActorResult(name=actor_name, photo_url=photo))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image, scene.site.base_url))
        for image_url in details_page_elements.xpath('//span[@id="trailer_thumb"]//img/@src').getall():
            images['push']((image_url or '').strip())

        metadata.art = images['list']
