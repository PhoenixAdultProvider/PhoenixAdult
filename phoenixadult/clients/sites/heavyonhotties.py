from __future__ import annotations

from typing import Any

from parsel import Selector

from phoenixadult.clients.base import Client, LoadedScene, LoadedSearch
from phoenixadult.models.scrape import SceneDetail, SearchContext
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr
from phoenixadult.utils.helpers.text import slugify
from phoenixadult.utils.helpers.urls import join_url

_RELEASED_XP = '//span[contains(@class,"released") and contains(@class,"title")]//strong'


def _search_title_strip(raw: str) -> str:
    after = raw.split(':', 1)[1] if ':' in raw else raw
    return after.strip().strip('"').strip()


def _detail_title_strip(raw: str) -> str:
    stripped = _search_title_strip(raw)
    return stripped.split(' - ')[-1].strip().strip('"')


def _lift_scheme(url: str) -> str:
    if not url:
        return ''

    return f'https:{url}' if url.startswith('//') else url


class HeavyOnHottiesClient(Client):
    candidate_include = ('/movies/',)
    candidate_exclude = ('/page-',)
    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def candidate_urls(self, search_data: SearchContext) -> list[str]:
        base = search_data.site_info.base_url.rstrip('/')
        words = search_data.title.strip().split()

        variants = [slugify(search_data.title)]
        if len(words) > 1:
            variants.append('-'.join(w.lower() for w in words[1:]))

        if len(words) > 2:
            tail = words[2:]
            if tail and tail[0].lower() == 'and':
                tail = tail[3:]

            joined = ' '.join(tail).replace("'", '')
            if joined:
                variants.append(slugify(joined))

        return list(dict.fromkeys(f'{base}/movies/{slug}' for slug in variants))

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        raw_h1 = source.sel.xpath('normalize-space((//h1)[1])').get() or ''
        return _search_title_strip(raw_h1) if raw_h1 else ''

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw_date = (source.sel.xpath(f'normalize-space(({_RELEASED_XP})[1])').get() or '').strip()
        return iso_date(raw_date) if raw_date else loaded.ctx.search_date

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = details_page_elements.xpath('normalize-space((//h1)[1])').get() or ''
        if not raw:
            return

        metadata.title = _detail_title_strip(raw) or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_attr(details_page_elements, 'normalize-space((//div[contains(@class,"video_text")])[1])') or ''

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = ['Heavy on Hotties']

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = (details_page_elements.xpath(f'normalize-space(({_RELEASED_XP})[1])').get() or '').strip()
        if date:
            metadata.release_date = iso_date(date)
            return

        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url.rstrip('/')

        def extract_photo(sel: Selector) -> str:
            raw = first_attr(sel, '(//div[h1]//img/@src)[1]')
            return _lift_scheme(raw) if raw else ''

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath('//span[contains(@class,"feature") and contains(@class,"title")]//a[contains(@href,"models")]'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name and href:
                refs.append((actor_name, join_url(href, base)))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(_lift_scheme)
        for image_url in details_page_elements.xpath('//video[@poster]/@poster').getall():
            images.push((image_url or '').strip())

        metadata.art = images.items
