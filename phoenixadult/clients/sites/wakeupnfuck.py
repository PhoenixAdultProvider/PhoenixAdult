from __future__ import annotations

import re
from typing import Any

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene, LoadedSearch
from phoenixadult.models.scrape import ActorResult, SceneDetail, SearchContext
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text, script_match
from phoenixadult.utils.helpers.urls import absolute_url, append_unique

_CARD_XP = '//a[contains(@class,"scene") and contains(@class,"item") and contains(@class,"light_background")]'
_IMAGE_RE = re.compile(r'image:\s*"([^"]+)"')


class WakeUpNFuckClient(Client):
    search_url_xpath = '@href'
    title_xpath = '//div[contains(@class,"block")]//h2'
    genres_xpath = '//div[contains(@class,"tags")]//a'

    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        url = search_data.search_url()
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search "{search_data.title}"')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath(_CARD_XP))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        title = first_text(source, './/h3')
        if not title:
            return ''

        actors = first_text(source, './/p[contains(@class,"sub")]')
        return f'{title} [{actors}]' if actors else title

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        desc = first_text(details_page_elements, '//div[contains(@class,"description")]')
        parts = desc.split('Publish Date :')
        if len(parts) >= 2:
            date = parts[-1].strip()
            if date:
                parsed = iso_date(date, '%d %B %Y') or iso_date(date)
                if parsed:
                    metadata.release_date = parsed
                    return

        if scene.scene_date:
            metadata.release_date = iso_date(scene.scene_date) or scene.scene_date

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        entries: list[ActorResult] = []
        for actor_link in details_page_elements.xpath('//div[contains(@class,"starring")]//a[contains(@class,"item")]'):
            actor_name = first_text(actor_link, './/p')
            src = first_attr(actor_link, '(.//img/@src)[1]')
            photo = (absolute_url(src, base)) if src else ''
            entries.append(ActorResult(name=actor_name, photo_url=photo))

        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        images: list[str] = []

        def push(raw: str) -> None:
            append_unique(images, raw, base)

        for poster in details_page_elements.xpath('//video[contains(@class,"player_video")]/@poster').getall():
            push(poster)

        if not images:
            for script in details_page_elements.xpath('//script/text()').getall():
                push(script_match(script, _IMAGE_RE).strip())

        metadata.art = images
