from __future__ import annotations

import re
from typing import Any

from phoenixadult.clients.base import Client, LoadedScene, LoadedSearch
from phoenixadult.models.scrape import SceneDetail
from phoenixadult.utils.helpers.helpers import append_unique, title_distance_score
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text

_NON_ALNUM_RE = re.compile(r'[^a-z0-9]', re.IGNORECASE)
_SUBSITE_RE = re.compile(r'scene/(.*?)/')


def _norm(s: str) -> str:
    return _NON_ALNUM_RE.sub('', s).lower()


class FinishesTheJobClient(Client):
    search_url_xpath = '(.//a/@href)[1]'
    search_rows_xpath = '//div[contains(@class,"scene")]'
    title_xpath = '//span[@itemprop="name"]'
    summary_xpath = '//p[@itemprop="description"]'
    genres_xpath = '//p[contains(.,"Categories")]//a'
    actors_xpath = '//h2[contains(.,"Starring")]//a'

    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/h3[@itemprop="name"]')

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        return loaded.ctx.search_date

    async def fetch_search_score(self, source: Any, loaded: LoadedSearch) -> float | None:
        title = first_text(source, './/h3[@itemprop="name"]')
        footer_href = first_attr(source, '(.//div[contains(@class,"card-footer")]//a/@href)[1]')
        m = _SUBSITE_RE.search(footer_href)
        sub_site = m.group(1) if m else ''
        bad_subsite = _norm(sub_site) != _norm(loaded.site.name)
        return title_distance_score(loaded.ctx.title, title) - (10 if bad_subsite else 0)

    async def fetch_search_subsite(self, source: Any, loaded: LoadedSearch) -> str | None:
        return first_text(source, '(.//div[contains(@class,"card-footer")]//a)[1]') or None

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'Finishes The Job'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images: list[str] = []

        def push(raw: str) -> None:
            append_unique(images, raw, scene.site.base_url)

        for row in details_page_elements.xpath('//video[@poster]'):
            push(row.xpath('@poster').get() or '')

        title = first_text(details_page_elements, '//span[@itemprop="name"]').lower()
        if title:
            for row in details_page_elements.xpath('//div[contains(@class,"first-set")]//img'):
                alt = first_attr(row, '@alt').lower()
                if alt == title:
                    push(row.xpath('@src').get() or '')

        metadata.art = images
