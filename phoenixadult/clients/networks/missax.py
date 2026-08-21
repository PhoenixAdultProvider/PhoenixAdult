from __future__ import annotations

from typing import Any

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from phoenixadult.utils.helpers.helpers import absolute_url, iso_date
from phoenixadult.utils.helpers.html_helpers import absolute_first_attr, first_attr

_SEARCH_DATE_XP = (
    './/span[@class="update_thumb_date"] | .//span[@class="date"] | .//div[contains(@class,"updateDetails")]/p/span[2] | .//div[contains(@class,"update_date")]'
)
_CAST_XP = '//div[contains(@class,"update_block")]/span[@class="tour_update_models"]//a | //p[@class="dvd-scenes__data"][1]//a'


class MissaXClient(Client):
    search_url_xpath = '(.//a)[1]/@href'
    genres_xpath = '//span[contains(@class,"update_tags")]//a | //p[@class="dvd-scenes__data"][2]//a'

    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        url = search_data.search_url()
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {url}')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath('//div[@class="updateItem"] | //div[@class="photo-thumb video-thumb"] | //div[@class="update_details"]'))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return (source.xpath('(.//h4//a | .//p[@class="thumb-title"] | ./a[./preceding-sibling::a])[1]').xpath('string(.)').get() or '').strip()

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        return iso_date((source.xpath(f'({_SEARCH_DATE_XP})[1]').xpath('string(.)').get() or '').strip())

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _cast_names(self, sel: Any) -> list[str]:
        return [n for n in (first_attr(a, 'normalize-space(.)') for a in sel.xpath(_CAST_XP)) if n]

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        title = (
            details_page_elements.xpath('(//span[@class="update_title"] | //p[@class="raiting-section__title"])[1]').xpath('string(.)').get() or ''
        ).strip()
        if scene.site.name == 'House of Fyre':
            for name in self._cast_names(details_page_elements):
                suffix = f': {name}'
                if title.endswith(suffix):
                    title = title[: -len(suffix)]
                    break

        metadata.title = title or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        parts: list[str] = []
        for row in details_page_elements.xpath(
            '//span[@class="latest_update_description"] | //div[@class="container"]//p[@class="dvd-scenes__title"]/following-sibling::p'
        ):
            t = (row.xpath('string(.)').get() or '').replace('\xa0', '').strip()
            if t:
                parts.append(t)

        if not parts:
            return

        joined = '\n'.join(parts).replace('Includes:', '').replace('Synopsis:', '').split('You Might Also Like')[0].strip()

        metadata.summary = joined or ''

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        update = (
            (details_page_elements.xpath('(//span[@class="update_date"] | //span[contains(@class,"availdate")])[1]').xpath('string(.)').get() or '')
            .replace('Available to Members Now', '')
            .strip()
        )
        if update:
            metadata.release_date = iso_date(update) or scene.scene_date or None
            return

        dvd_text = details_page_elements.xpath('(//p[@class="dvd-scenes__data"])[1]').xpath('string(.)').get() or ''
        parts = dvd_text.split('|')
        dvd = parts[1].replace('Added:', '').strip() if len(parts) > 1 else ''

        metadata.release_date = (iso_date(dvd) if dvd else None) or scene.scene_date or None

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            return absolute_first_attr(sel, '(//img[contains(@class,"model_bio_thumb")])[1]/@src0_1x', base)

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath(_CAST_XP):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name:
                refs.append((actor_name, absolute_url(href, base) if href else ''))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, label='actor')

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        images = self.image_collector(lambda image: absolute_url(image, base))

        xpaths = (
            '//img[contains(@class,"update_thumb")]/@src0_4x',
            '//img[contains(@class,"update_thumb")]/@src0_1x',
        )
        for xpath in xpaths:
            for image_url in details_page_elements.xpath(xpath).getall():
                images.push(image_url)

        metadata.art = images.items
