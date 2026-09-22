from __future__ import annotations

import re
from typing import Any

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene, LoadedSearch
from phoenixadult.models.scrape import SceneDetail, SearchContext
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text, meta_content
from phoenixadult.utils.helpers.urls import absolute_url

_TITLE_FIXES: dict[str, str] = {' Analìa ': ' Analia ', ' Kary ': ' Kari '}
_TITLE_KEYWORDS: list[str] = ['casting', 'debut', 'mesmerized', 'porn casting', 'pov']


def _apply_title_fixes(raw: str) -> str:
    out = raw
    for find, replace in _TITLE_FIXES.items():
        out = out.replace(find, replace)

    return out


def _cleanup_title(raw: str, actor_names: list[str]) -> str:
    fixed = _apply_title_fixes(raw)
    if any(fixed.lower().startswith(kw) for kw in _TITLE_KEYWORDS):
        return fixed.replace('.', ':')

    out = fixed
    for name in actor_names:
        escaped = re.escape(name)
        out = re.split(rf'\.\s{escaped}', out, flags=re.IGNORECASE)[0]
        tail = re.split(rf'{escaped}\s\.', out, flags=re.IGNORECASE)
        out = tail[-1]

    return out.strip()


class SexMexClient(Client):
    search_url_xpath = '(.//a/@href)[1]'
    summary_xpath = '//div[contains(@class,"panel-body")]//p'

    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        encoded = search_data.title.lower().replace(' ', '+')
        url = search_data.search_url(encoded)
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search "{search_data.title}"')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath('//div[contains(@class,"thumbnail")]'))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/h5')

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw = first_text(source, './/p[contains(@class,"scene-date")]')
        return iso_date(raw) if raw else None

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _actor_names(self, scene: LoadedScene) -> list[str]:
        details_page_elements = scene.require_sel()

        return [
            first_attr(actor_link, 'normalize-space(.)')
            for actor_link in details_page_elements.xpath('//p[@class]//a')
            if first_attr(actor_link, 'normalize-space(.)')
        ]

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = first_text(details_page_elements, '//h4')
        if not raw:
            return

        metadata.title = _cleanup_title(raw, self._actor_names(scene)) or ''

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = meta_content(details_page_elements, 'keywords', 'name')
        actor_lower = {n.lower() for n in self._actor_names(scene)}
        genres: list[str] = []
        for raw_g in raw.split(','):
            genre_name = raw_g.strip()
            if genre_name and genre_name.lower() not in actor_lower and genre_name not in genres:
                genres.append(genre_name)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url.rstrip('/')

        def extract_photo(sel: Selector) -> str:
            return first_attr(sel, '(//img/@src)[1]')

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath('//p[@class]//a'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name and href:
                refs.append((actor_name, f'{base}/tour/{href}'))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture, label=scene.site.name)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url.rstrip('/')
        images = self.image_collector(lambda image: absolute_url((image or '').strip(), base).split('?')[0])
        for image_url in details_page_elements.xpath('//div[contains(@class,"thumbnail")]//img/@src').getall():
            images.push(image_url)

        for image_url in details_page_elements.xpath('//video/@poster').getall():
            images.push(image_url)

        metadata.art = images.items
