from __future__ import annotations

import json
import re
from typing import Any

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text

_ACTOR_SPLIT_RE = re.compile(r"['?]")


def _actor_from_description(description: str) -> str:
    parts = _ACTOR_SPLIT_RE.split(description)
    return parts[1].strip() if len(parts) > 1 else ''


class SicflicsClient(Client):
    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        url = search_data.search_url()
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search "{search_data.title}"')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath('//li[contains(@class,"col-sm-6") and contains(@class,"col-lg-4")]'))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def build_search_results(self, source: Any, loaded: LoadedSearch, results: list[SearchResult]) -> None:
        title = first_text(source, './/div[contains(@class,"vidtitle")]/p[1]')
        img_url = first_attr(source, '(.//div[contains(@class,"vidthumb")]//a[contains(@class,"diagrad")]//img/@src)[1]')
        scene_id = first_attr(source, '(.//a[@data-movie]/@data-movie)[1]')
        if not title or not scene_id:
            return

        desc_raw = first_text(source, './/div[contains(@class,"collapse")]/p')
        description = desc_raw.split(':', 1)[1].strip() if ':' in desc_raw else desc_raw
        raw_date = first_text(source, './/div[contains(@class,"vidtitle")]/p[2]')
        release_date = iso_date(raw_date) if raw_date else None

        base = loaded.site.base_url.rstrip('/')
        packed = json.dumps(
            {
                'sceneID': scene_id,
                'imgURL': absolute_url(img_url, loaded.site.base_url),
                'description': description,
            }
        )
        popup_url = f'{base}/v6/v6.pop.php?id={scene_id}'

        results.append(
            build_search_result(
                site=loaded.site,
                title=title,
                scene_url=popup_url,
                query=loaded.ctx.title,
                display_date=release_date,
                search_date=loaded.ctx.search_date,
                cur_id=pack_cur_id([packed]),
            )
        )

    # ── Context Loader ────────────────────────────────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        try:
            packed = json.loads(payload)
        except (ValueError, TypeError):
            return None

        base = site.base_url.rstrip('/')
        popup_url = f'{base}/v6/v6.pop.php?id={packed.get("sceneID", "")}'
        details_page_elements = await self.fetch_and_load(
            popup_url, FetchCtx(capture=ctx.capture if ctx else None, use_bypass=site.use_bypass), f'[{site.name}] popup {popup_url}'
        )
        if not details_page_elements:
            return None

        return LoadedScene(
            url=popup_url, site=site, capture=ctx.capture if ctx else None, sel=details_page_elements['sel'], html=details_page_elements['html'], extra=packed
        )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _packed(self, scene: LoadedScene) -> dict[str, Any]:
        return scene.extra if isinstance(scene.extra, dict) else {}

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = first_text(details_page_elements, '//h4[contains(@class,"red")]')

        metadata.title = raw.lower() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.summary = (self._packed(scene).get('description') or '').replace('\n', '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_text(details_page_elements, '//span[@title="Date Added"]')
        if not date:
            return

        tail = date.split(':', 1)[1].strip() if ':' in date else date

        metadata.release_date = iso_date(tail) if tail else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            (genre_link.xpath('normalize-space(.)').get() or '').replace('#', '')
            for genre_link in details_page_elements.xpath('//div[contains(@class,"vidwrap")]//p//a')
        ]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        actor_name = _actor_from_description(self._packed(scene).get('description') or '')

        metadata.actors = [ActorResult(name=actor_name)] if actor_name else []

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        img = (self._packed(scene).get('imgURL') or '').strip()

        metadata.art = [img] if img else []
