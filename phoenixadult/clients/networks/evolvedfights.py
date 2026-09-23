from __future__ import annotations

from typing import Any

from parsel import Selector

from phoenixadult.clients.base import Client, LoadedScene, LoadedSearch
from phoenixadult.models.scrape import SceneDetail, SearchContext
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import absolute_first_attr, first_attr
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.text import slugify
from phoenixadult.utils.helpers.urls import absolute_url

STUDIO = 'Evolved Fights Network'
_URL_CONTAINS = '/updates/'
_DATE_FMT = '%m/%d/%Y'


class EvolvedFightsClient(Client):
    candidate_include = (_URL_CONTAINS,)
    title_xpath = '(//title)[1]'

    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def candidate_urls(self, search_data: SearchContext) -> list[str]:
        slug = slugify(search_data.title)
        return [f'{search_data.site_info.base_url.rstrip("/")}/{slug}.html'] if slug else []

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw = (source.sel.xpath('(//span[contains(@class,"update_date")])[1]').xpath('string(.)').get() or '').strip()
        return iso_date(raw, _DATE_FMT) if raw else None

    def search_cur_id(self, scene_url: str, date: str | None, loaded: LoadedSearch) -> str:
        return pack_cur_id([p for p in (scene_url, date or loaded.ctx.search_date) if p])

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = (
            details_page_elements.xpath('(//span[contains(@class,"latest_update_description")])[1]').xpath('string(.)').get() or ''
        ).strip() or ''

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name if scene.site.name != STUDIO else ''

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [STUDIO]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = (details_page_elements.xpath('(//span[contains(@class,"update_date")])[1]').xpath('string(.)').get() or '').strip()

        metadata.release_date = (iso_date(date, _DATE_FMT) if date else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres = [
            genre_name
            for genre_name in (
                first_attr(genre_link, 'normalize-space(.)') for genre_link in details_page_elements.xpath('//span[contains(@class,"tour_update_tags")]//a')
            )
            if genre_name
        ]

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            return absolute_first_attr(sel, '(//img[contains(@class,"model_bio_thumb")])[1]/@src0_3x', base)

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath(
            '//div[contains(@class,"update_block_info") and contains(@class,"model_update_block_info")]//span[contains(@class,"tour_update_models")]//a'
        ):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name:
                refs.append((actor_name, absolute_url(href, base) if href else ''))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = first_attr(details_page_elements, '(//span[contains(@class,"model_update_thumb")]//img)[1]/@src0_4x')
        if not raw:
            return

        poster = absolute_url(raw, scene.site.base_url)
        out = [poster]
        poster2 = poster.replace('0-4x', '1-4x')
        if poster2 != poster:
            out.append(poster2)

        metadata.art = out
