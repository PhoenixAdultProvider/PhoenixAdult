from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, RawCaptureEntry, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import build_search_result, epoch_date, pack_cur_id

STUDIO = 'Bellesa'
_API = '/api/rest/v1'


class BellesaClient(Client):
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

    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        scene_id = ctx.scene_id if ctx.scene_id and ctx.scene_id.isdigit() else ''

        if scene_id:
            data = await self._get_json(base, f'videos?filter[id]={scene_id}', ctx.capture)
            video = data[0] if isinstance(data, list) and data else None
            if not isinstance(video, dict) or not video.get('title'):
                return
            date = epoch_date(video.get('posted_on'))
            results.append(
                build_search_result(
                    title=str(video['title']).strip(),
                    scene_url=str(video.get('id')),
                    query=ctx.title,
                    display_date=date,
                    search_date=ctx.search_date,
                    score=100,
                    cur_id=pack_cur_id([str(video.get('id')), date or '']),
                )
            )
            return

        data = await self._get_json(base, f'search?limit=40&order[relevance]=DESC&q={quote(ctx.title)}&providers=bellesa', ctx.capture)
        videos = data.get('videos') or [] if isinstance(data, dict) else []
        for v in videos:
            title = str(v.get('title') or '').strip()
            vid = v.get('id')
            if not title or vid is None:
                continue
            date = epoch_date(v.get('posted_on'))
            results.append(
                build_search_result(
                    title=title, scene_url=str(vid), query=ctx.title, display_date=date, search_date=ctx.search_date, cur_id=pack_cur_id([str(vid), date or ''])
                )
            )

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        base = site.base_url.rstrip('/')
        pipe = payload.find('|')
        scene_id = payload[:pipe] if pipe >= 0 else payload
        scene_date = payload[pipe + 1 :].strip() if pipe >= 0 else ''
        data = await self._get_json(base, f'videos?filter[id]={scene_id}', ctx.capture if ctx else None)
        video = data[0] if isinstance(data, list) and data else None
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

    def _v(self, scene: LoadedScene) -> dict[str, Any]:
        return scene.extra or {}

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.title = str(self._v(scene).get('title') or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.summary = str(self._v(scene).get('description') or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    def _tagline(self, scene: LoadedScene) -> str:
        providers = self._v(scene).get('content_provider') or []
        return str(providers[0].get('name')).strip() if providers and isinstance(providers[0], dict) else ''

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline(scene) or None

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        t = self._tagline(scene)
        metadata.collections = [t] if t else None

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = epoch_date(self._v(scene).get('posted_on')) or scene.scene_date

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        raw = self._v(scene).get('tags')
        tags = raw.split(',') if isinstance(raw, str) else (raw or [])
        genres = [str(t).strip() for t in tags if str(t).strip()]
        metadata.genres = genres or []

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        actors = [
            ActorResult(name=str(p.get('name') or '').strip(), photo_url=str(p.get('image') or '').strip())
            for p in (self._v(scene).get('performers') or [])
            if str(p.get('name') or '').strip()
        ]
        metadata.actors = actors or []

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        coll = self.image_collector()
        coll['push'](self._v(scene).get('image'))
        images: list[str] = coll['list']
        metadata.raw_image_urls = images or []
