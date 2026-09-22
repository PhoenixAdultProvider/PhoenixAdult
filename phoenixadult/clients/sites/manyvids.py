from __future__ import annotations

import json

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result


def _numeric_id(url: str) -> str:
    return (url.split('/')[-1] if url else '').split('-')[0]


class ManyvidsClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        scene_id = search_data.title.strip().split()[0] if search_data.title.strip() else ''
        if not scene_id:
            return

        scene_url = f'{base}{search_data.site_info.search_path}{scene_id}'
        search_results = await self.fetch_and_load(scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] sceneID {scene_id}')
        if not search_results:
            return

        raw = search_results['sel'].xpath('(//script[@type="application/ld+json"])[1]/text()').get() or ''
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            return

        title = (data.get('name') or '').strip()
        if not title:
            return

        date = iso_date(data['uploadDate']) if data.get('uploadDate') else None

        results.append(
            build_search_result(
                site=search_data.site_info,
                title=title,
                scene_url=scene_url,
                query=search_data.title,
                display_date=date,
                search_date=search_data.search_date,
                score=100 if _numeric_id(scene_url) == scene_id else None,
                cur_id=pack_cur_id([x for x in (scene_url, date) if x]),
            )
        )

    # ── Context Loader (detail is a JSON API) ─────────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        pipe = payload.find('|')
        url = payload[:pipe] if pipe >= 0 else payload
        fallback_date = payload[pipe + 1 :].strip() if pipe >= 0 else ''
        api_url = f'{site.base_url.rstrip("/")}/bff/store/video/{_numeric_id(url)}'
        details_page_elements = await self.fetch_json(api_url, FetchCtx(capture=ctx.capture if ctx else None, use_bypass=site.use_bypass))
        data = (details_page_elements or {}).get('data')
        if not data:
            return None

        return LoadedScene(url=url, site=site, scene_date=fallback_date or None, capture=ctx.capture if ctx else None, extra=data)

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.title = (scene.require_extra(dict).get('title') or '').strip()

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.summary = (scene.require_extra(dict).get('description') or '').strip()

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = ((scene.require_extra(dict).get('model') or {}).get('displayName') or '').strip()

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        name = ((scene.require_extra(dict).get('model') or {}).get('displayName') or '').strip()

        metadata.collections = [name] if name else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        values: list[str | None] = [tag.get('label') for tag in (scene.require_extra(dict).get('tagList') or [])]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        model = scene.require_extra(dict).get('model') or {}
        actor_name = (model.get('displayName') or '').strip()

        metadata.actors = [ActorResult(name=actor_name, photo_url=model.get('avatar') or '')] if actor_name else []

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        shot = scene.require_extra(dict).get('screenshot')

        metadata.art = [shot] if shot else []
