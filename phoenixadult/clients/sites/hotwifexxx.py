from __future__ import annotations

import re

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text, web_search_urls

_DESCRIPTION_RE = re.compile(r'description:\s*', re.IGNORECASE)
_RELEASED_XP = '//div[contains(@class,"released2") and contains(@class,"trailerStarr")]'
_CAST_XP = '//div[contains(@class,"trailerMInfo")]//span[contains(@class,"tour_update_models")]/a'


def _date_of(raw: str) -> str | None:
    seg = raw.split(',')[0].strip()
    return iso_date(seg) if seg else None


class HotwifeXXXClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        found = await web_search_urls(search_data.title, search_data.site_info)

        seen: set[str] = set()
        candidates: list[str] = []
        for u in found:
            if '/updates/' in u and '/tour_hwxxx/' in u and u not in seen:
                seen.add(u)
                candidates.append(u)

        for scene_url in candidates:
            search_results = await self.fetch_and_load(scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] {scene_url}')
            if not search_results:
                continue

            title = first_text(search_results['sel'], '//div[contains(@class,"trailerInfo")]//h2')
            if not title:
                continue

            date = _date_of(first_text(search_results['sel'], _RELEASED_XP))

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    display_date=date,
                    search_date=search_data.search_date,
                )
            )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '//div[contains(@class,"trailerInfo")]//h2') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = first_text(details_page_elements, '//div[contains(@class,"dvdDescription")]//p')

        metadata.summary = _DESCRIPTION_RE.sub('', raw, count=1).strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'HotwifeXXX'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.release_date = _date_of(first_text(details_page_elements, _RELEASED_XP)) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        count = len(details_page_elements.xpath(_CAST_XP))
        if group := self.group_genre_for(count):
            metadata.genres = [group]

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            raw = first_attr(sel, '(//div[contains(@class,"modelBioPic")]//img/@src0_3x)[1]')
            return absolute_url(raw, base) if raw else ''

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath(_CAST_XP):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name:
                refs.append((actor_name, absolute_url(href, base) if href else ''))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture, label='actor')

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image, scene.site.base_url))
        for image_url in details_page_elements.xpath('//span[@id="trailer_thumb"]//img/@src').getall():
            images['push']((image_url or '').strip())

        metadata.art = images['list']
