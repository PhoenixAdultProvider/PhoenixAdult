from __future__ import annotations

import re
from typing import Any

from parsel import Selector

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from phoenixadult.utils.helpers.helpers import iso_date, join_url
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text, meta_content

_BR_RE = re.compile(r'</?br\s*/?>', re.IGNORECASE)


class XillimiteClient(Client):
    search_url_xpath = '@href'
    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        url = search_data.search_url()
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search "{search_data.title}"')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath('//a[contains(@class,"movies")]'))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_attr(source, '(.//img/@alt)[1]')

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '//h1') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        nodes = details_page_elements.xpath('//div[@id="synopsis"]/node()').getall()
        raw_html = ''.join(nodes) if nodes else meta_content(details_page_elements, 'twitter:description', 'name')
        if not raw_html:
            return

        with_newlines = _BR_RE.sub('\n', raw_html)
        stripped = (Selector(text=f'<div>{with_newlines}</div>').xpath('string(.)').get() or '').strip()

        metadata.summary = stripped or ''

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        if not scene.scene_date:
            return

        metadata.release_date = iso_date(scene.scene_date) or scene.scene_date

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url.rstrip('/')
        entries: list[ActorResult] = []
        for img in details_page_elements.xpath('//div[contains(@class,"casting")]//div[contains(@class,"slider-xl")]//a[contains(@class,"movies")]//img'):
            actor_name = first_attr(img, '@alt')
            data_src = first_attr(img, '@data-src')
            photo = join_url(data_src, base) if data_src else ''
            entries.append(ActorResult(name=actor_name, photo_url=photo))

        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url.rstrip('/')
        images: list[str] = []

        def push(raw: str) -> None:
            raw = (raw or '').strip()
            if not raw:
                return

            abs_url = join_url(raw.replace('blur9/', '/'), base)
            if abs_url not in images:
                images.append(abs_url)

        for href in details_page_elements.xpath('//div[contains(@class,"covers")]//a[contains(@class,"cover")]/@href').getall():
            push(href)

        for href in details_page_elements.xpath('//div[contains(@class,"screenshots")]//div[contains(@class,"slides")]//a/@href').getall():
            push(href)

        metadata.art = images
