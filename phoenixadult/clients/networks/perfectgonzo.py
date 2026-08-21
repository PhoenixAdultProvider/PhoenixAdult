from __future__ import annotations

from typing import Any

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from phoenixadult.utils.helpers.helpers import absolute_url, iso_date
from phoenixadult.utils.helpers.html_helpers import absolute_first_attr, first_attr

STUDIO = 'Perfect Gonzo'
_SUMMARY_DIV = 'col-sm-8 col-md-8 no-padding-side'
_TAGS_DIV = 'col-sm-8 col-md-8 no-padding-side tag-container'
_ACTOR_DIV = 'col-sm-3 col-md-3 col-md-offset-1 no-padding-side'
_DATE_DIV = 'col-sm-6 col-md-6 no-padding-left no-padding-right text-right'


class PerfectGonzoClient(Client):
    search_url_xpath = '(.//a)[1]/@href'
    title_xpath = '(//h2)[1]'

    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        url = search_data.search_url()
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {url}')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath('//div[@class="itemm"]'))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_attr(source, '(.//a)[1]/@title')

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw = (source.xpath('(.//span[@class="nm-date"])[1]').xpath('string(.)').get() or '').strip()
        return (iso_date(raw) if raw else None) or loaded.ctx.search_date

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = (details_page_elements.xpath(f'(//div[@class="{_SUMMARY_DIV}"]/p)[1]').xpath('string(.)').get() or '').strip()

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = (details_page_elements.xpath(f'(//div[@class="{_DATE_DIV}"]/span)[1]').xpath('string(.)').get() or '').strip()
        if date:
            after = date.split('Added')[-1].strip()
            if after:
                metadata.release_date = iso_date(after)
                return

        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres: list[str] = []
        for genre_link in details_page_elements.xpath(f'//div[@class="{_TAGS_DIV}"]//a'):
            genre_name = first_attr(genre_link, 'normalize-space(.)').lower()
            if genre_name and genre_name not in genres:
                genres.append(genre_name)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            return absolute_first_attr(sel, '(//div[@class="col-md-8 bigmodelpic"]/img)[1]/@src', base)

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath(f'//div[@class="{_ACTOR_DIV}"]/p/a'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name and href:
                refs.append((actor_name, absolute_url(href, base)))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, label=scene.site.name)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image, scene.site.base_url))
        for poster in details_page_elements.xpath('//video/@poster').getall():
            images.push(poster)

        for img in details_page_elements.xpath('//ul[@class="bxslider_screenshots"]//img'):
            images.push(img.xpath('@src').get() or img.xpath('@data-original').get())

        metadata.art = images.items
