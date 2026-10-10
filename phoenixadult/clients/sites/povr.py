from __future__ import annotations

import json
from typing import Any

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result
from phoenixadult.utils.helpers.urls import absolute_url
from phoenixadult.utils.processors.similarity import compare_string


def _parse_ld(sel: Selector) -> dict[str, Any] | None:
    text = first_attr(sel, '(//script[@type="application/ld+json"])[1]/text()')
    if not text:
        return None

    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except (ValueError, TypeError):
        return None


class POVRClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        scene_url = search_data.search_url()
        search_results = await self.fetch_and_load(scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {scene_url}')
        if not search_results:
            return

        for search_result in search_results['sel'].xpath('//div[contains(@class,"thumbnail-wrap")]/div'):
            title = first_attr(search_result, 'normalize-space((.//h6[contains(@class,"thumbnail__title")])[1])')
            href = first_attr(search_result, '(.//a[contains(@class,"thumbnail__link")]/@href)[1]')
            if not title or not href:
                continue

            url = absolute_url(href, search_data.site_info.base_url)
            sub_site = first_attr(search_result, 'normalize-space((.//a[contains(@class,"thumbnail__footer-link")])[1])')

            site_dist = compare_string(sub_site.lower().replace('originals', ''), search_data.site_info.name.lower()).levenshtein
            title_dist = compare_string(search_data.title.lower(), title.lower()).levenshtein
            score = 60 - (site_dist * 6) // 10 + (40 - (title_dist * 4) // 10)

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=url,
                    query=search_data.title,
                    search_date=search_data.search_date,
                    score=score,
                    cur_id=pack_cur_id([x for x in (url, sub_site) if x]),
                    subsite=sub_site or None,
                )
            )

    # ── Context Loader (ld+json detail; channel packed in curID) ──────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        pipe = payload.find('|')
        url = payload[:pipe] if pipe >= 0 else payload
        sub_site = payload[pipe + 1 :].strip() if pipe >= 0 else ''
        details_page_elements = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture if ctx else None), f'[{site.name}] scene {url}')
        if not details_page_elements:
            return None

        ld = _parse_ld(details_page_elements['sel'])
        if ld is None:
            return None

        return LoadedScene(
            url=url,
            site=site,
            capture=ctx.capture if ctx else None,
            sel=details_page_elements['sel'],
            html=details_page_elements['html'],
            extra={'ld': ld, 'subSite': sub_site},
        )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _ld(self, scene: LoadedScene) -> dict[str, Any]:
        return scene.extra.get('ld', {}) if isinstance(scene.extra, dict) else {}

    def _sub_site(self, scene: LoadedScene) -> str:
        return scene.extra.get('subSite', '') if isinstance(scene.extra, dict) else ''

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.title = (self._ld(scene).get('name') or '').strip()

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.summary = (self._ld(scene).get('description') or '').strip()

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = self._sub_site(scene) or scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [self._sub_site(scene) or scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        date = (self._ld(scene).get('uploadDate') or '').strip()

        metadata.release_date = iso_date(date) if date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            first_attr(genre_link, 'normalize-space(.)').lower() for genre_link in details_page_elements.xpath('//ul[contains(@class,"category-link")]//li//a')
        ]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        def extract_photo(sel: Selector) -> str:
            return (_parse_ld(sel) or {}).get('image') or ''

        refs: list[tuple[str, str]] = []
        for a in self._ld(scene).get('actor') or []:
            actor_name = (a.get('name') or '').strip()
            if not actor_name:
                continue

            refs.append((actor_name, (a.get('@id') or '').strip()))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        thumb = (self._ld(scene).get('thumbnailUrl') or '').strip()

        metadata.art = [thumb.replace('tiny', 'large')] if thumb else []
