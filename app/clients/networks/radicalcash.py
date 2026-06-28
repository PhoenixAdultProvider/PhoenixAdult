from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import build_search_result, iso_date, load_site_json, pack_cur_id

_PROFILES: dict[str, dict[str, str]] = load_site_json(__file__, 'radicalcash_profiles')
_DEFAULT = {'studio': 'Radical Cash', 'scene_path': '/videos'}


class RadicalCashClient(Client):
    def _profile(self, name: str) -> dict[str, str]:
        return _PROFILES.get(name, _DEFAULT)

    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        scene_path = self._profile(ctx.site_info.name)['scene_path']
        url = f'{base}/api/search/{quote(ctx.title.lower())}'
        data = await self.fetch_json(url, FetchCtx(capture=ctx.capture))
        scenes = data.get('scenes') or [] if isinstance(data, dict) else []

        results: list[SearchResult] = []
        for s in scenes:
            title = (s.get('title') or '').strip()
            slug = s.get('slug')
            if not title or not slug:
                continue
            scene_url = f'{base}{scene_path}/{slug}'
            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=ctx.title,
                    display_date=iso_date(s.get('publish_date') or ''),
                    search_date=ctx.search_date,
                    cur_id=pack_cur_id([scene_url]),
                )
            )
        return results

    # ── Context loader — fetch page, pull the embedded Next.js content blob ─────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        loaded = await self.fetch_and_load(payload, FetchCtx(capture=ctx.capture if ctx else None), f'[{site.name}] detail {payload}')
        if not loaded:
            return None
        raw = loaded['sel'].xpath('(//script[@type="application/json"])[1]/text()').get()
        if not raw:
            return None
        try:
            content = json.loads(raw)['props']['pageProps']['content']
        except (ValueError, KeyError, TypeError):
            return None
        if not isinstance(content, dict):
            return None
        return LoadedScene(url=payload, site=site, capture=ctx.capture if ctx else None, sel=loaded['sel'], html=loaded['html'], extra=content)

    def _content(self, scene: LoadedScene) -> dict[str, Any]:
        return scene.extra or {}

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        return (self._content(scene).get('title') or '').strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        summary = (self._content(scene).get('description') or '').strip()
        if summary and summary[-1] not in '.!?':
            summary += '.'
        return summary or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return self._profile(scene.site.name)['studio']

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        site = (self._content(scene).get('site') or '').strip()
        studio = self._profile(scene.site.name)['studio']
        return site if site and site != studio else None

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        site = (self._content(scene).get('site') or '').strip()
        return [site] if site else None

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        return iso_date(self._content(scene).get('publish_date') or '') or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        genres = [t.strip() for t in (self._content(scene).get('tags') or []) if t and t.strip()]
        return genres or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        actors = [
            ActorResult(name=(a.get('name') or '').strip(), photo_url=(a.get('thumb') or '').strip())
            for a in (self._content(scene).get('models_thumbs') or [])
            if (a.get('name') or '').strip()
        ]
        return actors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        content = self._content(scene)
        coll = self.image_collector()
        coll['push'](content.get('trailer_screencap'))
        for img in (content.get('previews') or {}).get('full', []):
            coll['push'](img)
        for img in content.get('extra_thumbnails') or []:
            coll['push'](img)
        if len(coll['list']) <= 4:
            for img in content.get('thumbs') or []:
                coll['push'](img)
        images: list[str] = coll['list']
        return images or None
