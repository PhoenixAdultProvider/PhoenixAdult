from __future__ import annotations

from typing import Any

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr
from phoenixadult.utils.helpers.search_results import build_search_result
from phoenixadult.utils.helpers.urls import absolute_url
from phoenixadult.utils.logging.logger import logger

_SCENE_URL_BLOCKLIST = ['/nude_girl/', '/shoots/', '/fetish/', '/updates/']
_LOCALE_PREFIXES = ['/cn/', '/de/', '/jp/', '/ja/', '/en/']


def _is_usable_scene_url(url: str) -> bool:
    return not any(bad in url for bad in _SCENE_URL_BLOCKLIST)


def _strip_locale(url: str) -> str:
    out = url
    for p in _LOCALE_PREFIXES:
        out = out.replace(p, '/')

    return out


def _parse_page_title(sel: Any) -> str:
    raw = sel.xpath('(//title)[1]/text()').get() or ''
    return raw.split(':')[-1].split('|')[0].strip()


__testing__ = {
    'is_usable_scene_url': _is_usable_scene_url,
    'strip_locale': _strip_locale,
    'SCENE_URL_BLOCKLIST': _SCENE_URL_BLOCKLIST,
    'LOCALE_PREFIXES': _LOCALE_PREFIXES,
}


class AbbyWintersClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        encoded = search_data.encoded.replace('%20', '+')
        search_url = search_data.search_url(encoded)

        search_results = await self.fetch_and_load(search_url, FetchCtx(capture=search_data.capture), f'GET {search_url}')
        if not search_results:
            return

        total_raw = first_attr(search_results['sel'], '(//span[@id="browse-total-count"])[1]/text()')
        if total_raw.isdigit() and int(total_raw) == 0:
            return

        model_hrefs: list[str] = []
        for href in search_results['sel'].xpath('//div[@id="browse-grid"]//main//article//a[@class]/@href').getall():
            if href:
                abs_url = absolute_url(href, search_data.site_info.base_url)
                if abs_url not in model_hrefs:
                    model_hrefs.append(abs_url)

        scene_urls: list[str] = []
        for _model_url, model_page_elements in await self.fetch_candidate_pages(
            model_hrefs, FetchCtx(capture=search_data.capture), lambda model_url: f'GET {model_url}'
        ):
            if not model_page_elements:
                continue

            for href in model_page_elements['sel'].xpath('//div[@id="subject-shoots"]//h2//a/@href').getall():
                if not href:
                    continue

                normalized = _strip_locale(absolute_url(href, search_data.site_info.base_url))
                if _is_usable_scene_url(normalized) and normalized not in scene_urls:
                    scene_urls.append(normalized)

        name = search_data.site_info.name
        logger.debug(name, f'AbbyWinters: {len(model_hrefs)} model page(s) -> {len(scene_urls)} scene URL(s)')

        actor_cache: dict[str, Any] = {}
        for scene_url in scene_urls:
            details_page_elements = await self.fetch_and_load(scene_url, FetchCtx(capture=search_data.capture), f'GET {scene_url}')
            if not details_page_elements:
                continue

            sel = details_page_elements['sel']
            title = _parse_page_title(sel)
            if not title:
                continue

            sub_site = (sel.xpath('(//div[@id="shoot-featured-image"]//h4)[1]').xpath('string(.)').get() or '').strip()
            display_date = await self._lookup_date(sel, search_data, title, sub_site, actor_cache)
            logger.debug(name, f'AbbyWinters: scene "{title}" [{sub_site}] -> date {display_date or "NOT FOUND"}')

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    display_date=display_date,
                    search_date=search_data.search_date,
                )
            )

    # ── Search Helpers ────────────────────────────────────────────────────────

    async def _lookup_date(self, sel: Any, search_data: SearchContext, title: str, sub_site: str, cache: dict[str, Any]) -> str | None:
        name = search_data.site_info.name
        model_link = sel.xpath('(//tr[contains(.,"Scene")]//a)[1]/@href').get()
        if not model_link:
            logger.debug(name, f'AbbyWinters._lookup_date: no model link for "{title}"')
            return None

        model_abs = absolute_url(model_link, search_data.site_info.base_url)
        model_sel = cache.get(model_abs)
        if model_sel is None:
            model_page_elements = await self.fetch_and_load(model_abs, FetchCtx(capture=search_data.capture), f'GET {model_abs} (model)')
            if not model_page_elements:
                logger.debug(name, f'AbbyWinters._lookup_date: model page fetch failed {model_abs}')
                return None

            model_sel = model_page_elements['sel']
            cache[model_abs] = model_sel

        cards = model_sel.xpath('//article[contains(@class,"card") and contains(@class,"card-shoot")]')
        logger.debug(name, f'AbbyWinters._lookup_date: matching "{title}"/"{sub_site}" against {len(cards)} card(s) on {model_abs}')
        for card in cards:
            h2 = (card.xpath('(.//h2)[1]').xpath('string(.)').get() or '').strip()
            h3 = ''.join(card.xpath('(.//h3)[1]//text()[not(ancestor::span)]').getall()).strip()
            if h2.lower() == title.lower() and h3.lower() == sub_site.lower():
                raw_date = (card.xpath('(.//span)[1]').xpath('string(.)').get() or '').strip()
                logger.debug(name, f'AbbyWinters._lookup_date: matched card -> raw date "{raw_date}"')
                return iso_date(raw_date)

        logger.debug(name, f'AbbyWinters._lookup_date: no card matched "{title}"/"{sub_site}"')
        return None

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _subsite(self, scene: LoadedScene) -> str:
        details_page_elements = scene.require_sel()

        return (details_page_elements.xpath('(//div[@id="shoot-featured-image"]//h4)[1]').xpath('string(.)').get() or '').strip()

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = _parse_page_title(details_page_elements) or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = (details_page_elements.xpath('(//aside//div[contains(@class,"description")])[1]').xpath('string(.)').get() or '').replace('\n', '').strip()

        metadata.summary = raw or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._subsite(scene) or ''

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        tagline = self._subsite(scene)

        metadata.collections = [tagline] if tagline else [scene.site.name]

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres = [
            genre_name
            for genre_name in (
                first_attr(genre_link, 'normalize-space(.)') for genre_link in details_page_elements.xpath('//aside//div[contains(@class,"description")]//a')
            )
            if genre_name
        ]

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            return first_attr(sel, '(//img[contains(@class,"img-responsive")]/@src)[1]')

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath('//tr[contains(.,"Scene")]//a'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name and href:
                refs.append((actor_name, absolute_url(href, base)))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector()
        xpaths = (
            '//div[contains(@class,"tile-image")]//img/@src',
            '//div[contains(@class,"video")]/@data-poster',
        )
        for xpath in xpaths:
            for image_url in details_page_elements.xpath(xpath).getall():
                images.push(image_url)

        metadata.art = images.items
