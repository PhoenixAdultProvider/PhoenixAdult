from __future__ import annotations

from typing import Any

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text, meta_content, web_search_urls
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result
from phoenixadult.utils.helpers.urls import absolute_url, to_https


def _title_or_text(node: Any) -> str:
    return (node.xpath('@title').get() or node.xpath('normalize-space(.)').get() or '').strip()


class VRLatinaClient(Client):
    title_xpath = '//h2'
    summary_xpath = '//div[contains(@class,"content-desc")]'

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

        for scene_url, details_page_elements in await self.fetch_candidate_pages(
            candidates, FetchCtx(capture=search_data.capture), lambda scene_url: f'[{search_data.site_info.name}] candidate {scene_url}'
        ):
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

        def extract_photo(sel: Selector) -> str:
            return first_attr(sel, '(//div[contains(@class,"model-avatar")]//img/@src)[1]')

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath('//div[contains(@class,"content-links") and contains(@class,"-models")]//a'):
            actor_name = _title_or_text(actor_link)
            href = first_attr(actor_link, '@href')
            if actor_name:
                refs.append((actor_name, absolute_url(href, base) if href else ''))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture, label=scene.site.name)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: to_https((image or '').strip()))
        for href in details_page_elements.xpath('//a[contains(@class,"video-gallery-item")]/@href').getall():
            images.push(href)

        images.push(meta_content(details_page_elements, 'og:image', 'property'))

        metadata.art = images.items
