from __future__ import annotations

from typing import Any

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from phoenixadult.utils.helpers.helpers import absolute_url, iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text, meta_content


def _holder_date(scope: Selector) -> str | None:
    dh = scope.xpath('//div[contains(@class,"date_holder")]')
    if not dh:
        return None

    spans = dh[0].xpath('./span')
    if not spans:
        return None

    month = (spans[0].xpath('normalize-space(.)').get() or '')[:3]
    inner = spans[0].xpath('.//span')
    year = first_attr(inner[0], 'normalize-space(.)') if inner else ''
    day = first_attr(spans[1], 'normalize-space(.)') if len(spans) > 1 else ''
    if month and day and year:
        return iso_date(f'{month} {day} {year}', '%b %d %Y')

    return None


class MomPOVClient(Client):
    search_url_xpath = '(.//div[contains(@class,"title_holder")]//h1//a/@href)[1]'
    summary_xpath = '//div[contains(@class,"entry_content")]//p'

    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        url = search_data.search_url()
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {url}')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath('//div[@id="inner_content"]//div[contains(@class,"entry")]'))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/div[contains(@class,"title_holder")]//h1//a')

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        return _holder_date(source)

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '//a[contains(@class,"title")]') or meta_content(details_page_elements, 'og:title', 'property') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'MomPOV'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.release_date = _holder_date(details_page_elements) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.genres = ['MILF']

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.actors = []

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        first_div = details_page_elements.xpath('//div[@id="inner_content"]/div')
        if not first_div:
            return

        raw = first_attr(first_div[0], '(.//a//img/@src)[1]')
        if not raw:
            return

        metadata.art = [absolute_url(raw, scene.site.base_url)]
