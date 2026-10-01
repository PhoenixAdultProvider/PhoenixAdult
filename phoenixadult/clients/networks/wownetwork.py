from __future__ import annotations

from typing import Any

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result
from phoenixadult.utils.helpers.urls import absolute_url

_SEARCH_PAGES = 5


class WowNetworkClient(Client):
    packed_scene_tail = True
    title_xpath = '(//h1[contains(@class,"entry-title")])[last()]'

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        slug = search_data.encoded

        async def fetch_rows(page: int) -> list[Any] | None:
            page_url = f'{base}/?s={slug}' if page == 1 else f'{base}/page/{page}/?s={slug}'
            search_results = await self.fetch_and_load(
                page_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search p{page} {page_url}'
            )
            return list(search_results['sel'].xpath('//article[contains(@class,"thumb-block")]')) if search_results else None

        def build_row(row: Any) -> SearchResult | None:
            anchor = row.xpath('(.//a)[1]')
            title = first_attr(anchor, '@title')
            href = first_attr(anchor, '@href')
            if not title or not href:
                return None

            scene_url = absolute_url(href, search_data.site_info.base_url)
            image = first_attr(row, '(.//img)[1]/@src')
            image_packed = self.encode(image) if image else ''
            return build_search_result(
                site=search_data.site_info,
                title=title,
                scene_url=scene_url,
                query=search_data.title,
                search_date=search_data.search_date,
                cur_id=pack_cur_id([scene_url, f'{search_data.search_date or ""}|{image_packed}']),
            )

        results.extend(await self.paginate_search(fetch_rows=fetch_rows, build_row=build_row, max_pages=_SEARCH_PAGES, stop_on_empty_page=True))

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = (details_page_elements.xpath('(//div[@id="video-date"])[1]').xpath('string(.)').get() or '').replace('Date:', '').strip()
        if date:
            metadata.release_date = iso_date(date)
            return

        meta = first_attr(details_page_elements, '(//meta[@property="article:published_time"])[1]/@content')
        if meta:
            metadata.release_date = iso_date(meta.split('T')[0])
            return

        metadata.release_date = iso_date(scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres = self.dedup_strings(
            [
                (genre_link.xpath('string(.)').get() or '').replace('Movies', '').strip()
                for genre_link in details_page_elements.xpath('//div[contains(@class,"tags-list")]//a[.//i[contains(@class,"fa-folder-open")]]')
            ]
        )

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        entries = [ActorResult(name=first_attr(actor_link, 'normalize-space(.)')) for actor_link in details_page_elements.xpath('//div[@id="video-actors"]//a')]

        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector()
        if b64 := scene.extra_or(str, ''):
            try:
                images.push(self.decode(b64))
            except (ValueError, TypeError):
                pass

        images.push(first_attr(details_page_elements, '(//meta[@property="og:image"])[1]/@content'))

        metadata.art = images.items
