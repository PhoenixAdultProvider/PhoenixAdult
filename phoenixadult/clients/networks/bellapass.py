from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, iso_date, slugify
from phoenixadult.utils.helpers.html_helpers import first_attr, web_search_urls

STUDIO = 'BellaPass'

_STUDIO_OVERRIDES: dict[str, str] = {'Babe Archives': 'Babe Archives', 'Hussie Pass': 'Hussie Pass', 'See Him Fuck': 'See Him Fuck'}
_TITLE_SELECTORS: dict[str, str] = {'Hussie Pass': 'h1', 'See Him Fuck': 'h1'}

_PUNCT_RE = re.compile(r'\s*[^\w\s]+')


def _studio_for(name: str) -> str:
    return _STUDIO_OVERRIDES.get(name, STUDIO)


def _title_selector_for(name: str) -> str:
    return _TITLE_SELECTORS.get(name, 'h3')


def _strip_punct(s: str) -> str:
    return _PUNCT_RE.sub('', s).strip()


def _title_from(sel: Any, primary: str) -> str:
    t = (sel.xpath(f'(//{primary})[1]').xpath('string(.)').get() or '').strip()
    if not t:
        other = 'h3' if primary == 'h1' else 'h1'
        t = (sel.xpath(f'(//{other})[1]').xpath('string(.)').get() or '').strip()

    return t


__testing__ = {'strip_punct': _strip_punct, 'studio_for': _studio_for, 'title_selector_for': _title_selector_for}


class BellaPassClient(Client):
    summary_xpath = '(//div[contains(@class,"videoDetails")]//p)[1]'

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        candidates: list[str] = [f'{base}/trailers/{slugify(search_data.title)}.html']

        enc = search_data.encoded.replace('%20', '-').lower()
        search_url = search_data.search_url(enc)
        search_results = await self.fetch_and_load(search_url, FetchCtx(capture=search_data.capture), f'GET {search_url}')
        if search_results:
            for search_result in search_results['sel'].xpath('//div[contains(@class,"item-video")]'):
                href = first_attr(search_result, '(./div)[1]//a[1]/@href')
                time = first_attr(search_result, '(.//div[contains(@class,"time")])[1]/text()')
                if not href or not re.match(r'^\d[\d:]*$', time):
                    continue

                abs_url = absolute_url(href, search_data.site_info.base_url)
                if abs_url not in candidates:
                    candidates.append(abs_url)

        found = await web_search_urls(search_data.title, search_data.site_info)

        for url in found:
            if '/trailers/' in url and url not in candidates:
                candidates.append(url)

        primary = _title_selector_for(search_data.site_info.name)
        for scene_url, details_page_elements in await self.fetch_candidate_pages(
            candidates, FetchCtx(capture=search_data.capture), lambda scene_url: f'GET {scene_url}'
        ):
            if not details_page_elements:
                continue

            title = _title_from(details_page_elements['sel'], primary)
            if not title:
                continue

            date_raw = (details_page_elements['sel'].xpath('(//div[contains(@class,"videoInfo")]//p)[1]').xpath('string(.)').get() or '').strip()
            release = iso_date(date_raw) or search_data.search_date

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    display_date=release,
                    search_date=search_data.search_date,
                )
            )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _title_of(self, scene: LoadedScene) -> str:
        details_page_elements = scene.require_sel()

        return _title_from(details_page_elements, _title_selector_for(scene.site.name))

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.title = self._title_of(scene) or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = _studio_for(scene.site.name)

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name if _studio_for(scene.site.name) == STUDIO else ''

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = (details_page_elements.xpath('(//div[contains(@class,"videoInfo")]//p)[1]').xpath('string(.)').get() or '').strip()

        metadata.release_date = iso_date(date) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres = [
            genre_name
            for genre_name in (
                first_attr(genre_link, 'normalize-space(.)')
                for genre_link in details_page_elements.xpath('//div[contains(@class,"featuring")]//a[contains(@href,"/categories/")]')
            )
            if genre_name
        ]
        cast = len(details_page_elements.xpath('//div[contains(@class,"featuring")]//a[contains(@href,"/models/")]'))
        if (group := self.group_genre_for(cast)) and group not in genres:
            genres.append(group)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url.rstrip('/')

        def extract_photo(sel: Selector) -> str:
            rel = first_attr(sel, '(//div[@class="profile-pic"]//img)[1]/@src0_3x')
            return (rel if rel.startswith('http') else base + rel) if rel else ''

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath('//div[contains(@class,"featuring")]//a[contains(@href,"/models/")]'):
            actor_name = _strip_punct(first_attr(actor_link, 'normalize-space(.)'))
            href = first_attr(actor_link, '@href')
            if actor_name:
                refs.append((actor_name, absolute_url(href, scene.site.base_url)))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url.rstrip('/')
        images = self.image_collector(lambda image: image if image.startswith('http') else base + image)

        xpaths = (
            '//img[contains(@class,"thumbs")]/@src0_3x',
            '//div[contains(@class,"item-thumb")]//img/@src0_3x',
        )
        for xpath in xpaths:
            for image_url in details_page_elements.xpath(xpath).getall():
                images.push(image_url)

        set_id = (
            details_page_elements.xpath('(//img[contains(@class,"thumbs")])[1]/@id').get()
            or details_page_elements.xpath('(//div[contains(@class,"item-thumb")]//img)[1]/@id').get()
            or ''
        ).strip()
        title = self._title_of(scene)
        if set_id and title:
            enc = quote(title, safe='').replace('%20', '+')
            search_page = scene.site.search_url(enc)
            search_results = await self.fetch_and_load(search_page, None, 'photoset search')
            if search_results:
                cnt_raw = search_results['sel'].xpath(f'(//img[@id="{set_id}"])[1]/@cnt').get() or '0'
                try:
                    cnt = int(cnt_raw)
                except ValueError:
                    cnt = 0

                for i in range(cnt):
                    images.push((search_results['sel'].xpath(f'(//img[@id="{set_id}"])[1]/@src{i}_3x').get() or '').strip())

            preview_page_elements = await self.fetch_and_load(scene.url.replace('/trailers/', '/preview/'), None, 'preview page')
            if preview_page_elements:
                for src in preview_page_elements['sel'].xpath(f'//img[@id="{set_id}"]/@src0_3x').getall():
                    images.push(src)

        metadata.art = images.items
