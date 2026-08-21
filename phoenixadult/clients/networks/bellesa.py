from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, RawCaptureEntry, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.helpers import build_search_result, epoch_date, pack_cur_id

STUDIO = 'Bellesa'
_API = '/api/rest/v1'


class BellesaClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        scene_id = search_data.scene_id if search_data.scene_id and search_data.scene_id.isdigit() else ''

        if scene_id:
            search_results = await self._get_json(base, f'videos?filter[id]={scene_id}', search_data.capture)
            video = search_results[0] if isinstance(search_results, list) and search_results else None
            if not isinstance(video, dict) or not video.get('title'):
                return

            date = epoch_date(video.get('posted_on'))

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=str(video['title']).strip(),
                    scene_url=str(video.get('id')),
                    query=search_data.title,
                    display_date=date,
                    search_date=search_data.search_date,
                    score=100,
                    cur_id=pack_cur_id([str(video.get('id')), date or '']),
                )
            )
            return

        search_results = await self._get_json(
            base, f'search?limit=40&order[relevance]=DESC&q={quote(search_data.title)}&providers=bellesa', search_data.capture
        )
        videos = search_results.get('videos') or [] if isinstance(search_results, dict) else []
        for v in videos:
            title = str(v.get('title') or '').strip()
            vid = v.get('id')
            if not title or vid is None:
                continue

            date = epoch_date(v.get('posted_on'))

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=str(vid),
                    query=search_data.title,
                    display_date=date,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([str(vid), date or '']),
                )
            )

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        base = site.base_url.rstrip('/')
        pipe = payload.find('|')
        scene_id = payload[:pipe] if pipe >= 0 else payload
        scene_date = payload[pipe + 1 :].strip() if pipe >= 0 else ''
        details_page_elements = await self._get_json(base, f'videos?filter[id]={scene_id}', ctx.capture if ctx else None)
        video = details_page_elements[0] if isinstance(details_page_elements, list) and details_page_elements else None
        if not isinstance(video, dict):
            return None

        return LoadedScene(
            url=f'{base}{_API}/videos?filter[id]={scene_id}',
            site=site,
            scene_date=scene_date or None,
            capture=ctx.capture if ctx else None,
            sel=None,
            html='',
            extra=video,
        )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    async def _get_json(self, base: str, path: str, capture: list[RawCaptureEntry] | None) -> Any:
        ctx = FetchCtx(capture=capture, use_bypass=True, headers={'Content-Type': 'application/json', 'Referer': base})
        loaded = await self.fetch_and_load(f'{base}{_API}/{path}', ctx, f'[Bellesa] {path}')
        if not loaded:
            return None

        body = loaded['sel'].xpath('(//body)[1]').xpath('string(.)').get() or ''
        try:
            return json.loads(body)
        except (ValueError, TypeError):
            return None

    def _v(self, scene: LoadedScene) -> dict[str, Any]:
        return scene.extra or {}

    def _tagline(self, scene: LoadedScene) -> str:
        providers = self._v(scene).get('content_provider') or []
        return str(providers[0].get('name')).strip() if providers and isinstance(providers[0], dict) else ''

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.title = str(self._v(scene).get('title') or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.summary = str(self._v(scene).get('description') or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline(scene) or ''

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        t = self._tagline(scene)

        metadata.collections = [t] if t else None

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = epoch_date(self._v(scene).get('posted_on')) or scene.scene_date

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        raw = self._v(scene).get('tags')
        tags = raw.split(',') if isinstance(raw, str) else (raw or [])
        genres = [str(t).strip() for t in tags if str(t).strip()]

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        actors = [
            ActorResult(name=str(p.get('name') or '').strip(), photo_url=str(p.get('image') or '').strip())
            for p in (self._v(scene).get('performers') or [])
            if str(p.get('name') or '').strip()
        ]

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        images = self.image_collector()
        images.push(self._v(scene).get('image'))

        metadata.art = images.items
