from __future__ import annotations

from urllib.parse import urlsplit

from parsel import Selector

from app.clients.base import Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, css_bg_image, iso_date, slugify
from app.utils.helpers.html_helpers import first_attr, first_text
from app.utils.logging.best_effort import best_effort
from app.utils.searchengines import SearchOptions, web_search

_DATE_XP = (
    '//span[contains(@class,"date-display-single")]'
    ' | //span[contains(@class,"u-inline-block") and contains(@class,"u-mr--nine")]'
    ' | //div[contains(@class,"video-meta-date")]'
    ' | //div[contains(@class,"date")]'
)


class LustRealityClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        candidates = [f'{base}{search_data.site_info.search_path}{slugify(search_data.title)}']
        host = urlsplit(search_data.site_info.base_url).hostname or ''
        with best_effort(search_data.site_info.name, 'webSearch'):
            for url in await web_search(SearchOptions(query=search_data.title, site=host, num=10)):
                if '/scene/' in url and url not in candidates:
                    candidates.append(url)

        for scene_url in candidates:
            search_results = await self.fetch_and_load(scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] {scene_url}')
            if not search_results:
                continue

            title = first_text(search_results['sel'], '//h1')
            if not title:
                continue

            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    display_date=iso_date(first_text(search_results['sel'], _DATE_XP)),
                    search_date=search_data.search_date,
                )
            )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '//h1') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_text(details_page_elements, '//div[contains(@class,"u-mb--six")]') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.release_date = iso_date(first_text(details_page_elements, _DATE_XP)) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            genre_link.xpath('normalize-space(.)').get() for genre_link in details_page_elements.xpath('//a[contains(@href,"/list/category/")]')
        ]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            raw = first_attr(sel, '(//div[contains(@class,"u-ratio--model-poster")]//img/@data-src)[1]')
            return absolute_url(raw, base) if raw else ''

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath('//a[contains(@href,"/pornstars/model/")]'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            if not actor_name:
                continue

            href = first_attr(actor_link, '@href')
            refs.append((actor_name, absolute_url(href, base) if href else ''))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image.strip(), scene.site.base_url))
        for el in details_page_elements.xpath('//div[contains(@class,"splash-screen")]'):
            images['push'](css_bg_image(el.xpath('@style').get()))

        for href in details_page_elements.xpath('//a[contains(@class,"u-ratio--lightbox")]/@href').getall():
            images['push'](href)

        metadata.art = images['list']
