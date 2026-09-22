from __future__ import annotations

import re

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import absolute_first_attr, first_attr
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result
from phoenixadult.utils.helpers.urls import absolute_url

_ORDINAL_RE = re.compile(r'(\d+)(st|nd|rd|th)\b', re.IGNORECASE)


def _cls(name: str) -> str:
    return f'contains(concat(" ",normalize-space(@class)," ")," {name} ")'


def _de_ordinal(raw: str) -> str:
    return _ORDINAL_RE.sub(r'\1', raw).strip()


class KarupsClient(Client):
    def __init__(self) -> None:
        super().__init__({'Cookie': 'warningHidden=hide'})

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        slug = re.sub(r'\s+', '-', search_data.title.strip())

        search_results = await self.fetch_and_load(
            f'{base}{search_data.site_info.search_path}{slug}/', FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] model search {slug}'
        )
        if not search_results:
            return

        model_href = first_attr(search_results['sel'], '(//div[contains(@class,"item-inside")]//a)[1]/@href')
        if not model_href:
            return

        model_page_elements = await self.fetch_and_load(
            absolute_url(model_href, search_data.site_info.base_url), FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] model page'
        )
        if not model_page_elements:
            return

        for card in model_page_elements['sel'].xpath('//div[contains(@class,"listing-videos")]//div[contains(@class,"item")]'):
            title = (card.xpath(f'(.//span[{_cls("title")}])[1]').xpath('string(.)').get() or '').strip()
            href = first_attr(card, '(.//a)[1]/@href')
            if not title or not href:
                continue

            scene_url = absolute_url(href, search_data.site_info.base_url)
            date = iso_date(_de_ordinal((card.xpath(f'(.//span[{_cls("date")}])[1]').xpath('string(.)').get() or '').strip()))

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    display_date=date,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([scene_url]),
                )
            )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _tagline(self, scene: LoadedScene) -> str:
        details_page_elements = scene.require_sel()

        return (details_page_elements.xpath('(//h1//span[contains(@class,"sup-title")]//span)[1]').xpath('string(.)').get() or '').strip() or scene.site.name

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = (details_page_elements.xpath(f'(//h1//span[{_cls("title")}])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = (
            details_page_elements.xpath('(//div[contains(@class,"content-information-description")]//p)[1]').xpath('string(.)').get() or ''
        ).strip() or ''

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline(scene)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [self._tagline(scene)]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        tagline = self._tagline(scene)
        date = (
            (details_page_elements.xpath(f'(//span[{_cls("date")}]//span[{_cls("content")}])[1]').xpath('string(.)').get() or '')
            .replace(tagline, '')
            .replace('Video added on', '')
            .strip()
        )

        metadata.release_date = (iso_date(_de_ordinal(date)) if date else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        tagline = self._tagline(scene)
        if tagline == 'KarupsHA':
            metadata.genres = ['Amateur']
        elif tagline == 'KarupsOW':
            metadata.genres = ['MILF']

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            return absolute_first_attr(sel, '(//div[contains(@class,"model-thumb")]//img)[1]/@src', base)

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath('//span[contains(@class,"models")]//a'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name:
                refs.append((actor_name, absolute_url(href, base) if href else ''))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, label='actor')

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image, scene.site.base_url))
        xpaths = (
            '(//div[contains(@class,"video-player")]//video)[1]/@poster',
            '//img[contains(@class,"poster")]/@src',
            '//div[contains(@class,"video-thumbs")]//img/@src',
        )
        for xpath in xpaths:
            for image_url in details_page_elements.xpath(xpath).getall():
                images.push(image_url)

        metadata.art = images.items
