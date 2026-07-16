from __future__ import annotations

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id, slugify
from app.utils.helpers.html_helpers import first_attr, web_search_urls

STUDIO = 'Thick Cash'


class ThickCashOtherClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        seen: set[str] = set()

        async def add_scene(scene_url: str) -> None:
            if scene_url in seen:
                return

            seen.add(scene_url)
            details_page_elements = await self.fetch_and_load(
                scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] candidate {scene_url}'
            )
            if not details_page_elements:
                return

            title = (details_page_elements['sel'].xpath('(//h3[contains(@class,"top-title")])[1]').xpath('string(.)').get() or '').strip()
            if not title:
                return

            results.append(
                build_search_result(
                    title=title, scene_url=scene_url, query=search_data.title, search_date=search_data.search_date, cur_id=pack_cur_id([scene_url])
                )
            )

        await add_scene(f'{base}/videos/{slugify(search_data.title)}.html')

        for u in await web_search_urls(search_data.title, search_data.site_info, include=['/videos/']):
            await add_scene(u)

        words = search_data.title.strip().split()
        model_id = '-'.join(words[:2])
        if model_id:
            model_page_elements = await self.fetch_and_load(
                f'{base}/models/{model_id}.html', FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] model {model_id}'
            )
            if model_page_elements:
                for href in model_page_elements['sel'].xpath('//div[contains(@class,"model-grid")]//a/@href').getall():
                    href = href.strip()
                    if href:
                        await add_scene(absolute_url(href, search_data.site_info.base_url))

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = (details_page_elements.xpath('(//h3[contains(@class,"top-title")])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = (details_page_elements.xpath('(//div[contains(@class,"player-box")]//p)[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        entries = [
            ActorResult(name=first_attr(actor_link, 'normalize-space(.)'))
            for actor_link in details_page_elements.xpath('//a[contains(@class,"tag") and contains(@href,"models")]')
        ]

        metadata.actors = self.dedup_people(entries) or []

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector()
        for image_url in details_page_elements.xpath('//video/@poster').getall():
            images['push'](image_url)

        metadata.art = images['list'] or []
