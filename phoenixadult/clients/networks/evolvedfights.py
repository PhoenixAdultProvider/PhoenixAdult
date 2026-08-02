from __future__ import annotations

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, iso_date, slugify
from phoenixadult.utils.helpers.html_helpers import first_attr, web_search_urls

STUDIO = 'Evolved Fights Network'
_URL_CONTAINS = '/updates/'
_DATE_FMT = '%m/%d/%Y'


class EvolvedFightsClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        candidates: list[str] = []
        slug = slugify(search_data.title)
        if slug:
            candidates.append(f'{base}/{slug}.html')

        for url in await web_search_urls(search_data.title, search_data.site_info, include=[_URL_CONTAINS]):
            if url not in candidates:
                candidates.append(url)

        for url, details_page_elements in await self.fetch_candidate_pages(
            candidates, FetchCtx(capture=search_data.capture), lambda url: f'[{search_data.site_info.name}] candidate {url}'
        ):
            if not details_page_elements:
                continue

            title = (details_page_elements['sel'].xpath('(//title)[1]').xpath('string(.)').get() or '').strip()
            if not title:
                continue

            raw = (details_page_elements['sel'].xpath('(//span[contains(@class,"update_date")])[1]').xpath('string(.)').get() or '').strip()
            date_iso = iso_date(raw, _DATE_FMT) if raw else None

            results.append(
                build_search_result(
                    site=search_data.site_info, title=title, scene_url=url, query=search_data.title, display_date=date_iso, search_date=search_data.search_date
                )
            )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = (details_page_elements.xpath('(//title)[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = (
            details_page_elements.xpath('(//span[contains(@class,"latest_update_description")])[1]').xpath('string(.)').get() or ''
        ).strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

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
            raw = first_attr(sel, '(//img[contains(@class,"model_bio_thumb")])[1]/@src0_3x')
            return absolute_url(raw, base) if raw else ''

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
