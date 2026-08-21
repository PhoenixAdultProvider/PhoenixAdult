from __future__ import annotations

from typing import Any

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from phoenixadult.utils.helpers.helpers import absolute_url, iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text

_FIXED_GENRES: list[str] = ['BDSM', 'Breast Torture', 'Breasts', 'Fetish', 'HuCows', 'Nipple Torture', 'Nipples']


class HucowsClient(Client):
    search_url_xpath = '(.//a/@href)[2]'
    summary_xpath = '//article//div[contains(@class,"entry-content")]//p'
    actors_xpath = '//a[@rel="tag"]'

    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        base = search_data.site_info.base_url.rstrip('/')
        if search_data.search_date:
            y, m = search_data.search_date.split('-')[:2]
            url = f'{base}/{y}/{m}'
        else:
            url = f'{base}/?s={search_data.title.strip().replace(" ", "+")}'

        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {url}')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath('//article'))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, '(.//h1|.//h2)')

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw = first_text(source, './/div[@itemprop="datePublished"]')
        return iso_date(raw) if raw else None

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = first_text(details_page_elements, '//head//title').replace(' - HuCows.com', '').strip()

        metadata.title = raw or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'HuCows'

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = ['HuCows']

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_text(details_page_elements, '//div[@itemprop="datePublished"]').replace('Release Date:', '').strip()

        metadata.release_date = (iso_date(date, '%d %b %Y') if date else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres = list(_FIXED_GENRES)
        for genre_link in details_page_elements.xpath('//a[@rel="category tag"]'):
            genre_name = first_attr(genre_link, 'normalize-space(.)')
            if genre_name and genre_name not in genres:
                genres.append(genre_name)

        metadata.genres = genres

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image.strip(), scene.site.base_url))
        for image_url in details_page_elements.xpath('//article//div//a[contains(@class,"lightboxhover")]//img/@src').getall():
            images.push(image_url)

        for image_url in details_page_elements.xpath('//center//a//img[contains(@class,"lightboxhover")]/@src').getall():
            images.push(image_url)

        metadata.art = images.items
