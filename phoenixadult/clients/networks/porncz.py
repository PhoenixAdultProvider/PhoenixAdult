from __future__ import annotations

from typing import Any

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene, LoadedSearch
from phoenixadult.models.scrape import ActorResult, SceneDetail, SearchContext
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr
from phoenixadult.utils.helpers.urls import absolute_url

_DOLLS_SITE = 'Czech Real Dolls'


class PornCZClient(Client):
    title_xpath = '(//h1)[1]'
    summary_xpath = '(//div[contains(@class,"dmb-1")]/p)[1]'

    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        slug = search_data.title.strip().lower().replace(' ', '+').replace('--', '+')
        url = search_data.search_url(slug)
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {url}')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath('//div[contains(@class,"card--item")]'))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return (source.xpath('(.//div[contains(@class,"card-body")]/a)[1]').xpath('string(.)').get() or '').strip()

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//div[contains(@class,"card-body")]/a)[1]/@href')
        return absolute_url(href, loaded.site.base_url) if href else ''

    async def fetch_search_thumb_url(self, source: Any, loaded: LoadedSearch) -> str | None:
        thumb = first_attr(source, '(.//div[contains(@class,"card__img")]//img)[1]/@data-src')
        if not thumb:
            return None

        return absolute_url(thumb, loaded.site.base_url)

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_attr(details_page_elements, '(//meta[@property="video:release_date"])[1]/@content')
        if date:
            metadata.release_date = iso_date(date, '%d.%m.%Y')
            return

        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            (genre_link.xpath('string(.)').get() or '').split('#')[-1].strip()
            for genre_link in details_page_elements.xpath('//div[contains(@class,"video-info")]//a[contains(@href,"?category=")]')
        ]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        is_dolls = scene.site.name == _DOLLS_SITE
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for actor_link in details_page_elements.xpath('//div[contains(@class,"mini-avatars")]/a'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if not actor_name or actor_name in seen:
                continue

            seen.add(actor_name)
            photo = ''
            gender = ''
            if href:
                model_page_elements = await self.fetch_and_load(absolute_url(href, base), None, f'[{scene.site.name}] actor {actor_name}')
                if model_page_elements:
                    raw = first_attr(model_page_elements['sel'], '(//img[contains(@class,"actor-img")])[1]/@data-src')
                    if raw and 'blank' not in raw:
                        photo = absolute_url(raw, base)

                    gender = (
                        (model_page_elements['sel'].xpath('(//div[contains(@class,"model-info__item")]//span[i])[1]').xpath('string(.)').get() or '')
                        .lower()
                        .strip()
                    )

            display = f'{actor_name} (Sex Doll)' if is_dolls and gender == 'female' else actor_name
            actors.append(ActorResult(name=display, photo_url=photo, gender=gender))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image, scene.site.base_url))
        xpaths = (
            '//a[contains(@class,"gallery-popup")]/@href',
            '//video[contains(@class,"video-player")]/@data-poster',
        )
        for xpath in xpaths:
            for image_url in details_page_elements.xpath(xpath).getall():
                images.push(image_url)

        metadata.art = images.items
