from __future__ import annotations

from typing import Any

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene, LoadedSearch
from phoenixadult.models.scrape import SceneDetail, SearchContext
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import absolute_first_attr, first_attr
from phoenixadult.utils.helpers.urls import absolute_url

STUDIO = 'Puffy Network'
_SEARCH_CARD = '//div[@style="position:relative; background:black;"]'


class PuffyClient(Client):
    search_url_xpath = '(.//a)[1]/@href'
    title_xpath = '(//div/section[1]/div[2]/h2/span)[1]'

    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        url = search_data.search_url()
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {url}')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath(_SEARCH_CARD))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_attr(source, '(.//a)[1]/@title')

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        return loaded.ctx.search_date

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        all_text = (details_page_elements.xpath('(//div/section[3]/div[2])[1]').xpath('string(.)').get() or '').strip()
        if not all_text:
            return

        tags = (details_page_elements.xpath('(//div/section[3]/div[2]/p)[1]').xpath('string(.)').get() or '').strip()
        summary = all_text.replace(tags, '') if tags else all_text

        metadata.summary = summary.split('Show more...')[0].strip()

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = (details_page_elements.xpath('(//div/section[2]/dl/dt[2])[1]').xpath('string(.)').get() or '').replace('Released on:', '').strip()
        if date:
            metadata.release_date = iso_date(date)
            return

        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres = self.dedup_strings([first_attr(genre_link, 'normalize-space(.)') for genre_link in details_page_elements.xpath('//div/section[3]/div[2]/p/a')])
        cast = len(details_page_elements.xpath('//div/section[2]/dl/dd[1]/a'))
        if (group := self.group_genre_for(cast)) and group not in genres:
            genres.append(group)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            return absolute_first_attr(sel, '(//div/section[1]/div/div[1]/img)[1]/@src', base)

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath('//div/section[2]/dl/dd[1]/a'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name:
                refs.append((actor_name, absolute_url(href, base) if href else ''))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, label=scene.site.name)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        images: list[str] = []

        parts = scene.url.split('-video-')
        if len(parts) > 1:
            cover = parts[1]
            host = scene.site.name.lower().replace(' ', '')
            images.append(f'https://media.{host}.com/videos/video-{cover}cover/hd.jpg')

        for image_url in details_page_elements.xpath('//div[contains(@id,"pics")]//img/@src').getall():
            if not image_url:
                continue

            abs_url = absolute_url(image_url, base)
            if abs_url not in images:
                images.append(abs_url)

        metadata.art = images
