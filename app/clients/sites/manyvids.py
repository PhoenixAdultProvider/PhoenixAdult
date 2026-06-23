from __future__ import annotations

import json
from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id


def _numeric_id(url: str) -> str:
    return (url.split('/')[-1] if url else '').split('-')[0]


class ManyvidsClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        scene_id = ctx.title.strip().split()[0] if ctx.title.strip() else ''
        if not scene_id:
            return []
        scene_url = f'{base}{ctx.site_info.search_path}{scene_id}'
        loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] sceneID {scene_id}')
        if not loaded:
            return []
        raw = loaded['sel'].xpath('(//script[@type="application/ld+json"])[1]/text()').get() or ''
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            return []
        title = (data.get('name') or '').strip()
        if not title:
            return []
        date = iso_date(data['uploadDate']) if data.get('uploadDate') else None
        return [
            build_search_result(
                title=title,
                scene_url=scene_url,
                query=ctx.title,
                display_date=date,
                search_date=ctx.search_date,
                score=100 if _numeric_id(scene_url) == scene_id else None,
                cur_id=pack_cur_id([x for x in (scene_url, date) if x]),
            )
        ]

    # ── Context loader (detail is a JSON API) ─────────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        pipe = payload.find('|')
        url = payload[:pipe] if pipe >= 0 else payload
        fallback_date = payload[pipe + 1 :].strip() if pipe >= 0 else ''
        api_url = f'{site.base_url.rstrip("/")}/bff/store/video/{_numeric_id(url)}'
        body = await self.fetch_json(api_url, FetchCtx(capture=ctx.capture if ctx else None))
        data = (body or {}).get('data')
        if not data:
            return None
        return LoadedScene(url=url, site=site, scene_date=fallback_date or None, capture=ctx.capture if ctx else None, extra=data)

    def _data(self, scene: LoadedScene) -> dict[str, Any]:
        assert isinstance(scene.extra, dict)
        return scene.extra

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        return (self._data(scene).get('title') or '').strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        return (self._data(scene).get('description') or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return 'ManyVids'

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return ((self._data(scene).get('model') or {}).get('displayName') or '').strip() or None

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        name = ((self._data(scene).get('model') or {}).get('displayName') or '').strip()
        return [name] if name else None

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        return scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        values: list[str | None] = [tag.get('label') for tag in (self._data(scene).get('tagList') or [])]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        model = self._data(scene).get('model') or {}
        name = (model.get('displayName') or '').strip()
        return [ActorResult(name=name, photo_url=model.get('avatar') or '')] if name else []

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        shot = self._data(scene).get('screenshot')
        return [shot] if shot else []
