from __future__ import annotations

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text, meta_content
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result
from phoenixadult.utils.helpers.urls import absolute_url, append_unique, to_https
from phoenixadult.utils.logging.logger import logger

_TITLE_XP = '//h1[contains(@class,"latest-scene-title")]'
_DATE_XP = '//p[contains(@class,"publish-date")]'
_ACTOR_LINK_XP = '//p[contains(@class,"model-name")]//a[contains(@href,"/models/")]'
_ACTOR_PHOTO_XP = '//img[@id="model-thumbnail"]/@src'


class VRAllureClient(Client):
    summary_xpath = '//p[contains(@class,"desc")]//span'
    genres_xpath = '//a[contains(@class,"label") and contains(@class,"label-tag")]'

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        slug = search_data.title.replace(' ', '_')
        if not slug:
            return

        search_url = f'{base}{search_data.site_info.search_path}{slug}'
        search_results = await self.fetch_and_load(search_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] direct {search_url}')
        if not search_results:
            return

        title = first_text(search_results['sel'], _TITLE_XP)
        if not title:
            return

        canonical = first_attr(search_results['sel'], '(//link[@rel="canonical"]/@href)[1]')
        scene_url = canonical or search_url
        date_raw = first_text(search_results['sel'], _DATE_XP)
        date = iso_date(date_raw) if date_raw else None
        logger.info(search_data.site_info.name, f'VRAllure direct hit "{title}" ({scene_url})')

        results.append(
            build_search_result(
                site=search_data.site_info,
                title=title,
                scene_url=scene_url,
                query=search_data.title,
                display_date=date,
                search_date=search_data.search_date,
                cur_id=pack_cur_id([scene_url, date or '']),
            )
        )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, _TITLE_XP) or ''

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_text(details_page_elements, _DATE_XP)
        if date:
            parsed = iso_date(date)
            if parsed:
                metadata.release_date = parsed
                return

        if scene.scene_date:
            metadata.release_date = iso_date(scene.scene_date) or scene.scene_date

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            return to_https((sel.xpath(f'({_ACTOR_PHOTO_XP})[1]').get() or '').strip())

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath(_ACTOR_LINK_XP):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name:
                refs.append((actor_name, absolute_url(href, base) if href else ''))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture, label=scene.site.name)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        images: list[str] = []

        def push(raw: str) -> None:
            append_unique(images, raw)

        push(to_https(meta_content(details_page_elements, 'og:image')))
        for href in details_page_elements.xpath(f'{_ACTOR_LINK_XP}/@href').getall():
            href = (href or '').strip()
            if not href:
                continue

            url = absolute_url(href, base)
            model_page_elements = await self.fetch_and_load(url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor-art {url}')
            if model_page_elements:
                push(to_https((model_page_elements['sel'].xpath(f'({_ACTOR_PHOTO_XP})[1]').get() or '').strip()))

        metadata.art = images
