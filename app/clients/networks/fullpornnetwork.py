from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from parsel import Selector

from app.clients.base import Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr
from app.utils.searchengines import SearchOptions, web_search, web_search_available

STUDIO = 'Full Porn Network'


def _after_colon(text: str) -> str:
    i = text.find(':')
    return (text[i + 1 :] if i >= 0 else text).strip()


class FullPornNetworkClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        host = urlsplit(search_data.site_info.base_url).netloc.removeprefix('www.')
        q = search_data.title.strip()

        google: list[str] = []
        if web_search_available():
            try:
                google = await web_search(SearchOptions(query=q, site=host, num=10))
            except Exception:  # noqa: BLE001 - best-effort
                google = []

        direct_slug = q.replace(' ', '-').lower() if q.count(' ') > 1 else q.replace(' ', '')
        model_urls: list[str] = [f'{base}/models/{direct_slug}.html']
        trailer_urls: list[str] = []
        for url in google:
            if '/trailers/' in url and url not in trailer_urls:
                trailer_urls.append(url)

            if '/models/' in url and 'models_' not in url and 'join' not in url and url not in model_urls:
                model_urls.append(url)

        seen: set[str] = set()

        for scene_url in trailer_urls:
            if scene_url in seen:
                continue

            search_results = await self.fetch_and_load(scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] trailer {scene_url}')
            if not search_results:
                continue

            title = _after_colon(search_results['sel'].xpath('(//h1[contains(@class,"title_bar")])[1]').xpath('string(.)').get() or '')
            if not title:
                continue

            date_raw = (search_results['sel'].xpath('(//div[contains(@class,"video-info")]//p)[1]').xpath('string(.)').get() or '').strip()
            date_iso = iso_date(date_raw) if date_raw else None
            seen.add(scene_url)
            carried = date_iso or search_data.search_date or ''

            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=q,
                    display_date=date_iso,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([x for x in (scene_url, carried) if x]),
                )
            )

        def harvest(sel: Any) -> None:
            for el in sel.xpath('//div[contains(@class,"latest-updates")]//div[@data-setid]'):
                href = first_attr(el, '(.//a[@class="updateimg"])[1]/@href')
                if not href:
                    continue

                scene_url = absolute_url(href, search_data.site_info.base_url)
                if scene_url in seen:
                    continue

                title = _after_colon(el.xpath('string(.)').get() or '')
                if not title:
                    continue

                seen.add(scene_url)

                results.append(build_search_result(title=title, scene_url=scene_url, query=q, search_date=search_data.search_date))

        for model_url in model_urls:
            search_results = await self.fetch_and_load(model_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] model {model_url}')
            if not search_results:
                continue

            harvest(search_results['sel'])
            next_href = first_attr(search_results['sel'], '(//a[contains(@class,"pagenav")])[1]/@href')
            if next_href:
                next_page_elements = await self.fetch_and_load(
                    absolute_url(next_href, search_data.site_info.base_url), FetchCtx(capture=search_data.capture), 'GET model page 2'
                )
                if next_page_elements:
                    harvest(next_page_elements['sel'])

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = _after_colon(details_page_elements.xpath('(//h1[contains(@class,"title_bar")])[1]').xpath('string(.)').get() or '') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = (
            details_page_elements.xpath('(//div[contains(@class,"video-description")]//p[contains(@class,"description-text")])[1]').xpath('string(.)').get()
            or ''
        ).strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = (details_page_elements.xpath('(//div[contains(@class,"video-info")]//p)[1]').xpath('string(.)').get() or '').strip()

        metadata.release_date = (iso_date(date) if date else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        out = [
            genre_name
            for genre_name in (
                first_attr(genre_link, 'normalize-space(.)')
                for genre_link in details_page_elements.xpath('//div[contains(@class,"video-info")]//a[contains(@href,"/categories/")]')
            )
            if genre_name
        ]

        metadata.genres = out or []

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            raw = first_attr(sel, '(//img[@alt="model"])[1]/@src0_3x')
            return absolute_url(raw, base) if raw else ''

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath('//div[contains(@class,"video-info")]//a[contains(@href,"/models/")]'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name and href:
                refs.append((actor_name, absolute_url(href, base)))

        if not refs:
            return

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: (image if 'http' in image else absolute_url(image, scene.site.base_url)).replace('-1x.jpg', '-3x.jpg'))
        for image_url in details_page_elements.xpath('//video/@poster').getall():
            images['push'](image_url)

        metadata.art = images['list'] or []
