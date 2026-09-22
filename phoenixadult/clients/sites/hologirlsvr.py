from __future__ import annotations

from urllib.parse import quote

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result
from phoenixadult.utils.helpers.urls import absolute_url, append_unique


class HoloGirlsVRClient(Client):
    title_xpath = '//div[contains(@class,"video-title")]//h3'
    genres_xpath = '//div[contains(@class,"videopage-tags")]//a'

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
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    search_date=search_data.search_date,
                    score=100,
                    cur_id=pack_cur_id([x for x in (scene_url, search_data.search_date) if x]),
                )
            )
            return

        search_url = search_data.search_url(quote(rest or search_data.title))
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
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=rest or search_data.title,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([x for x in (scene_url, search_data.search_date) if x]),
                )
            )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        nodes = details_page_elements.xpath('(//div[contains(@class,"vidpage-info")])[1]/text()').getall()
        if len(nodes) <= 4:
            return

        metadata.summary = nodes[4].strip() or ''

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
