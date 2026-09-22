from __future__ import annotations

from typing import Any

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene, LoadedSearch
from phoenixadult.models.scrape import SceneDetail
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import absolute_first_attr, first_attr, first_text
from phoenixadult.utils.helpers.urls import absolute_url

_ACTOR_XP = '//div[contains(@class,"pornstarnames")]//ul//li//a[contains(@href,"pornstars")]'


class FuckingAwesomeClient(Client):
    search_url_xpath = '(.//div[contains(@class,"video-title") and contains(@class,"truncate")]/a/@href)[1]'
    search_rows_xpath = '//div[contains(@class,"gallery")]/div'
    title_xpath = '//h1'
    summary_xpath = '//div[contains(@class,"more") and contains(@class,"text-justify")]'

    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/div[contains(@class,"video-title") and contains(@class,"truncate")]/a')

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw = first_text(source, './/span[contains(@class,"small") and contains(@class,"date")]')
        return iso_date(raw) if raw else None

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_text(details_page_elements, '//div[contains(@class,"videodate")]//strong')

        metadata.release_date = iso_date(date, '%B %d, %Y') or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres: list[str] = []
        for genre_link in details_page_elements.xpath('//div[contains(@class,"tags")]//ul//li//a'):
            genre_name = first_attr(genre_link, 'normalize-space(.)').lower()
            if genre_name and genre_name not in genres:
                genres.append(genre_name)

        count = len(details_page_elements.xpath(_ACTOR_XP))
        if (group := self.group_genre_for(count)) and group not in genres:
            genres.append(group)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            return absolute_first_attr(sel, '(//div[contains(@class,"pornstar-pic")]//img/@src)[1]', base)

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath(_ACTOR_XP):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name and href:
                refs.append((actor_name, absolute_url(href, base)))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture, label=scene.site.name)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url.rstrip('/')
        images = self.image_collector(lambda image: absolute_url((image or '').strip(), base))

        for image_url in details_page_elements.xpath('//span[contains(@class,"et_pb_image_wrap")]//img/@content').getall():
            images.push(image_url)

        photos_href = first_attr(details_page_elements, '(//li[contains(@class,"photos")]//a/@href)[1]')
        if photos_href:
            photos_url = absolute_url(photos_href, scene.site.base_url)
            photos_page_elements = await self.fetch_and_load(photos_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] photos page')
            if photos_page_elements:
                for image_url in photos_page_elements['sel'].xpath('//div[contains(@class,"my-gallery")]//a/@href').getall():
                    images.push(image_url)

        metadata.art = images.items
