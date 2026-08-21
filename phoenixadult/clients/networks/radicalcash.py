from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.helpers import build_search_result, iso_date, load_data, pack_cur_id

_PROFILES: dict[str, dict[str, str]] = load_data(__file__, 'radicalcash_profiles')
_DEFAULT = {'studio': 'Radical Cash', 'scene_path': '/videos'}


class RadicalCashClient(Client):
    def _profile(self, name: str) -> dict[str, str]:
        return _PROFILES.get(name, _DEFAULT)

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        scene_path = self._profile(search_data.site_info.name)['scene_path']
        url = f'{base}/api/search/{quote(search_data.title.lower())}'
        search_results = await self.fetch_json(url, FetchCtx(capture=search_data.capture))
        scenes = search_results.get('scenes') or [] if isinstance(search_results, dict) else []

        for s in scenes:
            title = (s.get('title') or '').strip()
            slug = s.get('slug')
            if not title or not slug:
                continue

            scene_url = f'{base}{scene_path}/{slug}'

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    display_date=iso_date(s.get('publish_date') or ''),
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([scene_url]),
                )
            )

    # ── Context Loader — Fetch Page, Pull the Embedded Next.js Content Blob ─────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        details_page_elements = await self.fetch_and_load(
            payload, FetchCtx(capture=ctx.capture if ctx else None, use_bypass=site.use_bypass), f'[{site.name}] detail {payload}'
        )
        if not details_page_elements:
            return None

        raw = details_page_elements['sel'].xpath('(//script[@type="application/json"])[1]/text()').get()
        if not raw:
            return None

        try:
            content = json.loads(raw)['props']['pageProps']['content']
        except (ValueError, KeyError, TypeError):
            return None

        if not isinstance(content, dict):
            return None

        return LoadedScene(
            url=payload, site=site, capture=ctx.capture if ctx else None, sel=details_page_elements['sel'], html=details_page_elements['html'], extra=content
        )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _content(self, scene: LoadedScene) -> dict[str, Any]:
        return scene.extra or {}

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.title = (self._content(scene).get('title') or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        summary = (self._content(scene).get('description') or '').strip()
        if summary and summary[-1] not in '.!?':
            summary += '.'

        metadata.summary = summary or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = self._profile(scene.site.name)['studio']

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        site = (self._content(scene).get('site') or '').strip()
        studio = self._profile(scene.site.name)['studio']

        metadata.tagline = site if site and site != studio else ''

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        site = (self._content(scene).get('site') or '').strip()

        metadata.collections = [site] if site else None

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = iso_date(self._content(scene).get('publish_date') or '') or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        genres = [t.strip() for t in (self._content(scene).get('tags') or []) if t and t.strip()]

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        actors = [
            ActorResult(name=(a.get('name') or '').strip(), photo_url=(a.get('thumb') or '').strip())
            for a in (self._content(scene).get('models_thumbs') or [])
            if (a.get('name') or '').strip()
        ]

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        content = self._content(scene)
        images = self.image_collector()
        images.push(content.get('trailer_screencap'))
        for img in (content.get('previews') or {}).get('full', []):
            images.push(img)

        for img in content.get('extra_thumbnails') or []:
            images.push(img)

        if len(images.items) <= 4:
            for img in content.get('thumbs') or []:
                images.push(img)

        metadata.art = images.items
