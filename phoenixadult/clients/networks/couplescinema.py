from __future__ import annotations

import re
from typing import ClassVar

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.scoring import title_distance_score
from phoenixadult.utils.helpers.search_results import build_search_result
from phoenixadult.utils.helpers.urls import absolute_url
from phoenixadult.utils.logging.logger import logger

_YEAR_RE = re.compile(r'^\d{4}$')


class CouplesCinemaClient(Client):
    summary_xpath = '(//span[contains(@class,"description")])[1]'

    default_headers: ClassVar[dict[str, str]] = {'Cookie': 'WarningModal=true'}

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')

        if search_data.scene_id:
            scene_url = f'{base}/post/details/{search_data.scene_id}'
            direct_page_elements = await self.fetch_and_load(
                scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] directScene {scene_url}'
            )
            if not direct_page_elements:
                return

            title = (
                direct_page_elements['sel'].xpath('(//div[contains(@class,"mediaHeader")]//span[contains(@class,"title")])[1]').xpath('string(.)').get() or ''
            ).strip()
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
                    cur_id=pack_cur_id([scene_url]),
                )
            )
            return

        slug = '+'.join(search_data.title.split())
        search_url = search_data.search_url(slug)
        search_results = await self.fetch_and_load(search_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {search_url}')
        if not search_results:
            return

        requested = search_data.site_info.name.lower()
        for search_result in search_results['sel'].xpath('//div[contains(@class,"Post")]'):
            title = (search_result.xpath('(.//span[contains(@class,"title")])[1]').xpath('string(.)').get() or '').strip()
            href = first_attr(search_result, '(.//a[contains(@class,"media")])[1]/@href')
            if not title or not href:
                continue

            scene_url = absolute_url(href, search_data.site_info.base_url)
            studio = (search_result.xpath('(.//span[contains(@class,"source")])[1]').xpath('string(.)').get() or '').strip()
            cover = first_attr(search_result, '(.//a[contains(@class,"media")]//img[contains(@class,"image")])[1]/@src')
            cover_packed = self.encode(cover) if cover else ''

            score: float = title_distance_score(search_data.title, title)
            if studio.lower() != requested:
                score -= 10

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    search_date=search_data.search_date,
                    score=score,
                    cur_id=pack_cur_id([scene_url, search_data.search_date or '', cover_packed]),
                )
            )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    @staticmethod
    def _date_part(scene: LoadedScene) -> str | None:
        return scene.scene_date.split('|')[0].strip() if scene.scene_date else None

    @staticmethod
    def _cover_part(scene: LoadedScene) -> str:
        if scene.scene_date and '|' in scene.scene_date:
            return scene.scene_date.split('|', 1)[1]

        return ''

    def _tagline(self, scene: LoadedScene) -> str | None:
        details_page_elements = scene.require_sel()

        raw = (details_page_elements.xpath('(//span[contains(@class,"type")])[1]').xpath('string(.)').get() or '').strip()
        return raw.split('|')[0].strip() or None

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = (
            details_page_elements.xpath('(//div[contains(@class,"mediaHeader")]//span[contains(@class,"title")])[1]').xpath('string(.)').get() or ''
        ).strip() or ''

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline(scene) or ''

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        tag = self._tagline(scene)

        metadata.collections = [tag] if tag else None

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date_part = self._date_part(scene)
        if date_part:
            metadata.release_date = iso_date(date_part) or date_part
            return

        date = (details_page_elements.xpath('(//span[contains(@class,"type")])[1]').xpath('string(.)').get() or '').strip()
        parts = [p.strip() for p in date.split('|')]
        year = parts[1] if len(parts) > 1 else ''

        metadata.release_date = f'{year}-01-01' if _YEAR_RE.match(year) else None

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        entries = [ActorResult(name=first_attr(actor_link)) for actor_link in details_page_elements.xpath('//div[contains(@class,"cast")]//a')]

        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image, scene.site.base_url))

        cover_packed = self._cover_part(scene)
        if cover_packed:
            try:
                images.push(self.decode(cover_packed))
            except Exception as err:  # noqa: BLE001 - decode failures are non-fatal
                logger.debug(scene.site.name, f'cover decode: {err}')

        for image_url in details_page_elements.xpath('//video/@poster').getall():
            images.push(image_url)

        metadata.art = images.items
