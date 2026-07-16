from __future__ import annotations

from urllib.parse import urlsplit

from app.clients.base import Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text
from app.utils.logging.logger import logger
from app.utils.searchengines import SearchOptions, web_search


class MeloneChallengeClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        host = urlsplit(search_data.site_info.base_url).netloc
        try:
            found = await web_search(SearchOptions(query=search_data.title, site=host, num=10))
        except Exception as err:  # noqa: BLE001 - search failure is non-fatal
            logger.warn(self.tag(search_data.site_info), f'webSearch threw: {err}')
            return

        candidates = list(dict.fromkeys(u for u in found if '/video/' in u))

        for scene_url in candidates:
            search_results = await self.fetch_and_load(scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] {scene_url}')
            if not search_results:
                continue

            title = first_text(search_results['sel'], '//a[contains(@class,"dark")]')
            if not title:
                continue

            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([x for x in (scene_url, search_data.search_date) if x]),
                )
            )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '//a[contains(@class,"dark")]') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'Melone Challenge'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = scene.scene_date or None

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image, scene.site.base_url))
        for el in details_page_elements.xpath('//figure//img'):
            images['push'](first_attr(el, '@src'))

        metadata.art = images['list']
