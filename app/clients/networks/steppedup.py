from __future__ import annotations

import json
from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id

STUDIO = 'Stepped Up Media'


class SteppedUpClient(Client):
    async def _build_id(self, probe_url: str, capture: Any) -> str | None:
        loaded = await self.fetch_and_load(probe_url, FetchCtx(capture=capture), f'buildId probe {probe_url}')
        if not loaded:
            return None
        raw = loaded['sel'].xpath('(//script[@type="application/json"])[1]/text()').get()
        if not raw:
            return None
        try:
            build_id = json.loads(raw).get('buildId')
        except (ValueError, TypeError):
            return None
        return str(build_id) if build_id else None

    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        query = ctx.title.split('and')[0].strip().replace(' ', '-').lower()
        if not query:
            return []
        build_id = await self._build_id(f'{base}/models/{query}', ctx.capture)
        if not build_id:
            return []
        data = await self.fetch_json(f'{base}/_next/data/{build_id}/models/{query}.json', FetchCtx(capture=ctx.capture))
        contents = (data.get('pageProps') or {}).get('model_contents') or [] if isinstance(data, dict) else []

        results: list[SearchResult] = []
        for s in contents:
            title = (s.get('title') or '').strip()
            slug = s.get('slug')
            if not title or not slug:
                continue
            date = iso_date(s.get('publish_date') or '')
            results.append(
                build_search_result(
                    title=title, scene_url=slug, query=ctx.title, display_date=date, search_date=ctx.search_date, cur_id=pack_cur_id([slug, date or ''])
                )
            )
        return results

    # ── Context loader — probe buildId, fetch the scene JSON ────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        base = site.base_url.rstrip('/')
        pipe = payload.find('|')
        slug = payload[:pipe] if pipe >= 0 else payload
        scene_date = payload[pipe + 1 :].strip() if pipe >= 0 else ''
        build_id = await self._build_id(f'{base}/scenes/{slug}', ctx.capture if ctx else None)
        if not build_id:
            return None
        data = await self.fetch_json(f'{base}/_next/data/{build_id}/scenes/{slug}.json', FetchCtx(capture=ctx.capture if ctx else None))
        content = (data.get('pageProps') or {}).get('content') if isinstance(data, dict) else None
        if not isinstance(content, dict):
            return None
        return LoadedScene(
            url=f'{base}/scenes/{slug}', site=site, scene_date=scene_date or None, capture=ctx.capture if ctx else None, sel=None, html='', extra=content
        )

    def _c(self, scene: LoadedScene) -> dict[str, Any]:
        return scene.extra or {}

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        return (self._c(scene).get('title') or '').strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        return (self._c(scene).get('description') or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    def _tagline(self, scene: LoadedScene) -> str:
        return (self._c(scene).get('site') or '').strip()

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return self._tagline(scene) or None

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        t = self._tagline(scene)
        return [t] if t else None

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        d = iso_date(self._c(scene).get('publish_date') or '')
        return d or (iso_date(scene.scene_date) or scene.scene_date if scene.scene_date else None)

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        genres = [t.strip() for t in (self._c(scene).get('tags') or []) if t and t.strip()]
        return genres or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        actors = [
            ActorResult(name=(a.get('name') or '').strip(), photo_url=(a.get('thumb') or '').strip())
            for a in (self._c(scene).get('models_thumbs') or [])
            if (a.get('name') or '').strip()
        ]
        return actors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        content = self._c(scene)
        coll = self.image_collector()
        coll['push'](content.get('trailer_screencap'))
        for key in ('extra_thumbnails', 'thumbs'):
            for img in content.get(key) or []:
                coll['push'](img)
        images: list[str] = coll['list']
        return images or None
