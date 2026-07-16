from __future__ import annotations

from urllib.parse import quote

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, append_unique, build_search_result, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text


class HoloGirlsVRClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        scene_id = search_data.scene_id
        rest = search_data.title.strip()

        if scene_id and not rest:
            scene_url = f'{base}/Scenes/Videos/{scene_id}'
            search_results = await self.fetch_and_load(
                scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] directScene {scene_url}'
            )
            if not search_results:
                return

            title = first_text(search_results['sel'], '//div[contains(@class,"video-title")]//h3')
            if not title:
                return

            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    search_date=search_data.search_date,
                    score=100,
                    cur_id=pack_cur_id([x for x in (scene_url, search_data.search_date) if x]),
                )
            )
            return

        search_url = base + search_data.site_info.search_path.replace('{query}', quote(rest or search_data.title))
        search_results = await self.fetch_and_load(search_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {search_url}')
        if not search_results:
            return

        for search_result in search_results['sel'].xpath('//div[contains(@class,"memVid")]'):
            anchor = search_result.xpath('(.//div[contains(@class,"memVidTitle")]/a)[1]')
            title = first_attr(anchor, '@title')
            href = first_attr(anchor, '@href')
            if not title or not href:
                continue

            scene_url = absolute_url(href, search_data.site_info.base_url)

            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=rest or search_data.title,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([x for x in (scene_url, search_data.search_date) if x]),
                )
            )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '//div[contains(@class,"video-title")]//h3') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        nodes = details_page_elements.xpath('(//div[contains(@class,"vidpage-info")])[1]/text()').getall()
        if len(nodes) <= 4:
            return

        metadata.summary = nodes[4].strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            genre_link.xpath('normalize-space(.)').get() for genre_link in details_page_elements.xpath('//div[contains(@class,"videopage-tags")]//a')
        ]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        entries: list[ActorResult] = []
        for card in details_page_elements.xpath('//div[contains(@class,"col-md-3")]'):
            actor_name = first_text(card, './/div[contains(@class,"vidpage-mobilePad")]//a//strong')
            raw = first_attr(card, '(.//img[contains(@class,"imgHover")]/@src)[1]')
            photo = (absolute_url(raw, scene.site.base_url)) if raw else ''
            entries.append(ActorResult(name=actor_name, photo_url=photo))

        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images: list[str] = []

        def push(raw: str) -> None:
            append_unique(images, raw, scene.site.base_url)

        push(details_page_elements.xpath('(//div[contains(@class,"vidCover")]//img/@src)[1]').get() or '')
        for image_url in details_page_elements.xpath('//div[contains(@class,"vid-flex-container")]//span//img/@src').getall():
            push((image_url or '').replace('_thumb', ''))

        metadata.art = images
