from __future__ import annotations

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, pack_cur_id
from phoenixadult.utils.helpers.html_helpers import first_text, web_search_urls
from phoenixadult.utils.logging.best_effort import best_effort


class JVRPornClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        scene_id = search_data.scene_id
        rest = search_data.title.strip()

        candidates: list[str] = []
        if scene_id:
            candidates.append(f'{base}/video/{scene_id}')

        if rest:
            with best_effort(search_data.site_info.name, 'webSearch'):
                for url in await web_search_urls(rest, search_data.site_info):
                    if '/video/' in url and url not in candidates:
                        candidates.append(url)

        for scene_url, search_results in await self.fetch_candidate_pages(
            candidates, FetchCtx(capture=search_data.capture), lambda scene_url: f'[{search_data.site_info.name}] {scene_url}'
        ):
            if not search_results:
                continue

            title = first_text(search_results['sel'], '//h1')
            if not title:
                continue

            is_direct = scene_id is not None and scene_id in scene_url

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=rest or search_data.title,
                    search_date=search_data.search_date,
                    score=100 if is_direct else None,
                    cur_id=pack_cur_id([x for x in (scene_url, search_data.search_date) if x]),
                )
            )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '//h1') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_text(details_page_elements, '//pre') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'JVR Porn'

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = ['JVR Porn']

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [s.xpath('normalize-space(.)').get() for s in details_page_elements.xpath('//td[contains(@class,"tags")]//span')]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        entries = [ActorResult(name=s.xpath('normalize-space(.)').get() or '') for s in details_page_elements.xpath('//a[contains(@class,"actress")]//span')]

        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image.strip(), scene.site.base_url))
        for image_url in details_page_elements.xpath('//div[contains(@id,"snapshot-gallery")]//a/@href').getall():
            images.push(image_url)

        for image_url in details_page_elements.xpath('//deo-video/@cover-image').getall():
            images.push(image_url)

        metadata.art = images.items
