from __future__ import annotations

from typing import Any

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result
from phoenixadult.utils.helpers.urls import absolute_url, join_url


def _desc_row(sel: Any, label: str) -> str:
    return (sel.xpath(f'(//div[contains(@class,"player-scene-description")]//span[contains(text(),"{label}")]/..)[1]').xpath('string(.)').get() or '').strip()


class JulesJordanClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        seen: set[str] = set()

        direct_url = f'{base}/trial/scenes/{"-".join(search_data.title.lower().split())}_vids.html'
        direct_page_elements = await self.fetch_and_load(
            direct_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] directScene {direct_url}'
        )
        if direct_page_elements:
            seen.add(direct_url)

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=search_data.title,
                    scene_url=direct_url,
                    query=search_data.title,
                    search_date=search_data.search_date,
                    score=100,
                    cur_id=pack_cur_id([x for x in (direct_url, search_data.search_date) if x]),
                )
            )

        search_url = search_data.search_url()
        search_results = await self.fetch_and_load(search_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {search_url}')
        if search_results:
            for search_result in search_results['sel'].xpath('//div[contains(@class,"search-scene-card")] | //div[contains(@class,"grid-item")]'):
                href = first_attr(search_result, '(.//a[contains(@class,"jj-card-thumb")])[1]/@href') or first_attr(search_result, '(.//a)[1]/@href')
                title = (search_result.xpath('(.//h2[contains(@class,"jj-card-title")])[1]/text()').get() or '').strip() or first_attr(
                    search_result, '(.//a//img | .//img)[1]/@alt'
                )
                if not href or not title:
                    continue

                scene_url = absolute_url(href, search_data.site_info.base_url)
                if scene_url in seen:
                    continue

                seen.add(scene_url)

                date_raw = (search_result.xpath('(.//div[contains(@class,"jj-card-date")])[1]/text()').get() or '').replace('Released:', '').strip()
                release_date = iso_date(date_raw) if date_raw else None

                results.append(
                    build_search_result(
                        site=search_data.site_info,
                        title=title,
                        scene_url=scene_url,
                        query=search_data.title,
                        search_date=search_data.search_date,
                        display_date=release_date,
                        cur_id=pack_cur_id([x for x in (scene_url, release_date or search_data.search_date) if x]),
                    )
                )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        title = (details_page_elements.xpath('(//h1[contains(@class,"scene-title")])[1]/text()').get() or '').strip()
        metadata.title = title or (details_page_elements.xpath('(//div[contains(@class,"movie_title")])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        summary = (
            details_page_elements.xpath('(//div[contains(concat(" ",normalize-space(@class)," ")," scene-desc ")])[1]').xpath('string(.)').get() or ''
        ).strip()
        metadata.summary = summary or _desc_row(details_page_elements, 'Description:').replace('Description:', '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        dvd_name = (
            details_page_elements.xpath('(//div[contains(@class,"meta-item")]/div[text()="Movie"]/following-sibling::div)[1]/text()').get() or ''
        ).strip()
        metadata.tagline = dvd_name or _desc_row(details_page_elements, 'Movie:').replace('Movie:', '').replace('Feature: ', '').strip() or ''

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        if scene.scene_date:
            metadata.release_date = scene.scene_date
            return

        date = (
            details_page_elements.xpath('(//div[contains(@class,"meta-item")]/div[text()="Released"]/following-sibling::div)[1]/text()').get() or ''
        ).strip() or _desc_row(details_page_elements, 'Date:').replace('Date:', '').strip()

        metadata.release_date = iso_date(date) if date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres: list[str] = []
        for genre_link in details_page_elements.xpath('//div[contains(@class,"scene-cats")]/a | //span[contains(text(),"Categories")]//a'):
            genre_name = first_attr(genre_link, 'normalize-space(.)').lower()
            if genre_name and genre_name not in genres:
                genres.append(genre_name)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        anchors = details_page_elements.xpath(
            '//div[contains(@class,"scene-info")]//span[contains(@class,"update_models")]/a'
            ' | //div[contains(@class,"player-scene-description")]//span[contains(text(),"Starring:")]/..//a'
        )

        def extract_photo(sel: Selector) -> str:
            raw = first_attr(sel, '(//img[contains(@src,"contentthumbs")])[1]/@src') or first_attr(
                sel, '(//img[contains(@class,"model_bio_thumb")])[1]/@src0_3x'
            )
            return absolute_url(raw, base) if raw else ''

        refs: list[tuple[str, str]] = []
        for row in anchors:
            actor_name = first_attr(row, 'normalize-space(.)')
            href = first_attr(row, '@href')
            if actor_name:
                refs.append((actor_name, absolute_url(href, base) if href else ''))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, label='actor')

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url.rstrip('/')
        images = self.image_collector(lambda image: join_url(image, base))

        for photo in details_page_elements.xpath('//a[contains(@class,"tp-photo-thumb")]//img/@src | //div[contains(@class,"tp-photos-strip")]//img/@src'):
            images.push((photo.get() or '').strip())

        images.push(first_attr(details_page_elements, '(//video[@id="video-player"])[1]/@poster'))

        metadata.art = images.items
