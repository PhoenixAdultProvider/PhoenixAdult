from __future__ import annotations

from typing import Any

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id, to_https
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text, meta_content, web_search_urls


def _title_or_text(node: Any) -> str:
    return (node.xpath('@title').get() or node.xpath('normalize-space(.)').get() or '').strip()


class VRLatinaClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        slug = search_data.title.replace(' ', '-').lower()
        if not slug:
            return

        direct_url = f'{base}{search_data.site_info.search_path}{slug}.html'

        seen = {direct_url}
        candidates = [direct_url]
        for raw in await web_search_urls(search_data.title, search_data.site_info):
            if '/video/' in raw and raw not in seen:
                seen.add(raw)
                candidates.append(raw)

        for scene_url in candidates:
            details_page_elements = await self.fetch_and_load(
                scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] candidate {scene_url}'
            )
            if not details_page_elements:
                continue

            title = meta_content(details_page_elements['sel'], 'og:title')
            if not title:
                continue

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([scene_url, search_data.search_date or '']),
                )
            )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '//h2') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_text(details_page_elements, '//div[contains(@class,"content-desc")]') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_text(
            details_page_elements, '//div[contains(@class,"content-base-info")]//div[contains(@class,"info-elem") and contains(@class,"-length")]//span'
        )
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
            _title_or_text(genre_link) for genre_link in details_page_elements.xpath('//div[contains(@class,"content-links") and contains(@class,"-tags")]//a')
        ]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for actor_link in details_page_elements.xpath('//div[contains(@class,"content-links") and contains(@class,"-models")]//a'):
            actor_name = _title_or_text(actor_link)
            href = first_attr(actor_link, '@href')
            if not actor_name or actor_name in seen:
                continue

            seen.add(actor_name)
            photo = ''
            if href:
                url = absolute_url(href, base)
                model_page_elements = await self.fetch_and_load(url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {actor_name}')
                if model_page_elements:
                    photo = first_attr(model_page_elements['sel'], '(//div[contains(@class,"model-avatar")]//img/@src)[1]')

            actors.append(ActorResult(name=actor_name, photo_url=photo))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: to_https((image or '').strip()))
        for href in details_page_elements.xpath('//a[contains(@class,"video-gallery-item")]/@href').getall():
            images['push'](href)

        images['push'](details_page_elements.xpath('(//meta[@property="og:image"]/@content)[1]').get() or '')

        metadata.art = images['list']
