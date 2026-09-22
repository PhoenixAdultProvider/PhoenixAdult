from __future__ import annotations

from typing import Any

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene, LoadedSearch
from phoenixadult.models.scrape import ActorResult, SceneDetail, SearchContext
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr
from phoenixadult.utils.helpers.urls import absolute_url

_ANCHOR = './/div[contains(@class,"video_item--content")]//a'
_DATE_FMT = '%d %b %Y'


class SinXClient(Client):
    title_xpath = '(//h1[contains(@class,"title--3")])[1]'
    summary_xpath = '(//div[h5]//p)[1]'

    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        url = search_data.search_url()
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {url}')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath('//div[contains(@class,"view_grid--container")]'))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return (source.xpath(f'({_ANCHOR})[1]/@title').get() or '').strip()

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = (source.xpath(f'({_ANCHOR})[1]/@href').get() or '').strip()
        return absolute_url(href, loaded.site.base_url) if href else ''

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = (details_page_elements.xpath('(//tr[td[contains(.,"Date")]]/td[2])[1]').xpath('string(.)').get() or '').strip()
        if date:
            metadata.release_date = iso_date(date, _DATE_FMT) or iso_date(date)
            return

        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres = self.dedup_strings(
            [
                (genre_link.xpath('string(.)').get() or '').split('#')[-1].strip()
                for genre_link in details_page_elements.xpath('//div[contains(@class,"tags-wrap")]//a')
            ]
        )
        cast = len(details_page_elements.xpath('//figure[contains(@class,"girls-item")]'))
        if (group := self.group_genre_for(cast)) and group not in genres:
            genres.append(group)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        figures = details_page_elements.xpath('//figure[contains(@class,"girls-item")]')
        single = len(figures) == 1
        entries: list[ActorResult] = []
        for fig in figures:
            actor_name = (fig.xpath('(.//h4)[1]').xpath('string(.)').get() or '').strip()
            photo = first_attr(fig, '(.//img)[1]/@src') if single else ''
            entries.append(ActorResult(name=actor_name, photo_url=photo))

        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image, scene.site.base_url))
        for src in details_page_elements.xpath('//div[contains(@class,"video__block") and contains(@class,"video_item--player")]//img/@src').getall():
            images.push(src)

        metadata.art = images.items
