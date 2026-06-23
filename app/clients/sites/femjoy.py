from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import (
    build_search_result,
    date_distance_score,
    iso_date,
    pack_cur_id,
    title_distance_score,
)

_HTML_TAG_RE = re.compile(r'<[^>]+>')


@dataclass
class _FemjoyExtra:
    result: dict[str, Any]
    date_fallback: str


class FemjoyClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        query = ctx.title
        effective_date = ctx.search_date or ''
        search_url = base + ctx.site_info.search_path.replace('{query}', quote(query))

        data = await self.fetch_json(search_url, FetchCtx(capture=ctx.capture), label=f'GET {search_url}')
        results: list[SearchResult] = []
        for r in (data or {}).get('results', []):
            scene_id = r.get('id')
            title = r.get('title')
            if not scene_id or not title:
                continue
            date_iso = iso_date(r.get('release_date') or '') or effective_date
            score = date_distance_score(effective_date, date_iso) if (effective_date and date_iso) else title_distance_score(query, title)
            results.append(
                build_search_result(
                    title=title,
                    scene_url=search_url,
                    query=query,
                    display_date=date_iso or None,
                    search_date=effective_date or None,
                    score=score,
                    cur_id=pack_cur_id([search_url, f'{date_iso or ""}|{scene_id}']),
                )
            )
        return results

    # ── Context loader (re-query the JSON, find the result by id) ─────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        first_pipe = payload.find('|')
        search_url = payload[:first_pipe] if first_pipe >= 0 else payload
        tail = payload[first_pipe + 1 :] if first_pipe >= 0 else ''
        date_fallback, _, id_str = tail.partition('|')
        try:
            scene_id = int(id_str)
        except ValueError:
            return None

        data = await self.fetch_json(search_url, FetchCtx(capture=ctx.capture if ctx else None), label=f'GET {search_url}')
        result = next((r for r in (data or {}).get('results', []) if r.get('id') == scene_id), None)
        if not result or not result.get('title'):
            return None
        return LoadedScene(
            url=search_url,
            site=site,
            scene_date=date_fallback or None,
            capture=ctx.capture if ctx else None,
            extra=_FemjoyExtra(result=result, date_fallback=date_fallback),
        )

    def _extra(self, scene: LoadedScene) -> _FemjoyExtra:
        assert isinstance(scene.extra, _FemjoyExtra)
        return scene.extra

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        return self._extra(scene).result.get('title') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        return _HTML_TAG_RE.sub('', self._extra(scene).result.get('long_description') or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        extra = self._extra(scene)
        return iso_date(extra.result.get('release_date') or '') or extra.date_fallback or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        actors = await self.fetch_actors(scene) or []
        n = len(actors)
        if n == 3:
            return ['Threesome']
        if n == 4:
            return ['Foursome']
        if n > 4:
            return ['Orgy']
        return []

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for a in self._extra(scene).result.get('actors', []):
            name = a.get('name')
            if not name or name in seen:
                continue
            seen.add(name)
            photo = (a.get('thumb') or {}).get('image') or ''
            if photo.endswith('noimageavailable.gif'):
                photo = await self._actor_thumb_fallback(scene.site, name, a.get('id')) or photo
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors

    async def _actor_thumb_fallback(self, site: ResolvedSiteInfo, name: str, actor_id: Any) -> str:
        first_name = name.split()[0] if name.split() else ''
        lookup = f'{site.base_url.rstrip("/")}/api/v2/search/actors?thumb_size=355x475&query={quote(first_name)}'
        data = await self.fetch_json(lookup)
        match = next((x for x in (data or {}).get('results', []) if x.get('id') == actor_id), None)
        return (match.get('thumb') or {}).get('image') or '' if match else ''

    async def fetch_directors(self, scene: LoadedScene) -> list[ActorResult] | None:
        directors = [ActorResult(name=d['name']) for d in self._extra(scene).result.get('directors', []) if d.get('name')]
        return directors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        image = (self._extra(scene).result.get('thumb') or {}).get('image')
        return [image] if image else []
