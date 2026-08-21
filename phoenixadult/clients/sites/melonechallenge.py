from __future__ import annotations

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, pack_cur_id
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text, web_search_urls


class MeloneChallengeClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        found = await web_search_urls(search_data.title, search_data.site_info)

        candidates = list(dict.fromkeys(u for u in found if '/video/' in u))

        for scene_url, search_results in await self.fetch_candidate_pages(
            candidates, FetchCtx(capture=search_data.capture), lambda scene_url: f'[{search_data.site_info.name}] {scene_url}'
        ):
            if not search_results:
                continue

            title = first_text(search_results['sel'], '//a[contains(@class,"dark")]')
            if not title:
                continue

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([x for x in (scene_url, search_data.search_date) if x]),
                )
            )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '//a[contains(@class,"dark")]') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'Melone Challenge'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image, scene.site.base_url))
        for row in details_page_elements.xpath('//figure//img'):
            images.push(first_attr(row, '@src'))

        metadata.art = images.items
