from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.helpers import (
    build_search_result,
    date_distance_score,
    iso_date,
    pack_cur_id,
    title_distance_score,
)
from phoenixadult.utils.helpers.html_helpers import strip_tags


@dataclass
class _FemjoyExtra:
    result: dict[str, Any]
    date_fallback: str


class FemjoyClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        query = search_data.title
        effective_date = search_data.search_date or ''
        search_url = search_data.search_url(quote(query))

        search_results = await self.fetch_json(search_url, FetchCtx(capture=search_data.capture), label=f'GET {search_url}')
        for r in (search_results or {}).get('results', []):
            scene_id = r.get('id')
            title = r.get('title')
            if not scene_id or not title:
                continue

            date_iso = iso_date(r.get('release_date') or '') or effective_date
            score = date_distance_score(effective_date, date_iso) if (effective_date and date_iso) else title_distance_score(query, title)

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=search_url,
                    query=query,
                    display_date=date_iso or None,
                    search_date=effective_date or None,
                    score=score,
                    cur_id=pack_cur_id([search_url, f'{date_iso or ""}|{scene_id}']),
                )
            )

    # ── Context Loader (re-query the JSON, find the result by id) ─────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        first_pipe = payload.find('|')
        search_url = payload[:first_pipe] if first_pipe >= 0 else payload
        tail = payload[first_pipe + 1 :] if first_pipe >= 0 else ''
        date_fallback, _, id_str = tail.partition('|')
        try:
            scene_id = int(id_str)
        except ValueError:
            return None

        details_page_elements = await self.fetch_json(
            search_url, FetchCtx(capture=ctx.capture if ctx else None, use_bypass=site.use_bypass), label=f'GET {search_url}'
        )
        result = next((r for r in (details_page_elements or {}).get('results', []) if r.get('id') == scene_id), None)
        if not result or not result.get('title'):
            return None

        return LoadedScene(
            url=search_url,
            site=site,
            scene_date=date_fallback or None,
            capture=ctx.capture if ctx else None,
            extra=_FemjoyExtra(result=result, date_fallback=date_fallback),
        )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _extra(self, scene: LoadedScene) -> _FemjoyExtra:
        assert isinstance(scene.extra, _FemjoyExtra)
        return scene.extra

    def _unique_actor_count(self, scene: LoadedScene) -> int:
        seen: set[str] = set()
        for a in self._extra(scene).result.get('actors', []):
            actor_name = a.get('name')
            if actor_name and actor_name not in seen:
                seen.add(actor_name)

        return len(seen)

    async def _actor_thumb_fallback(self, site: ResolvedSiteInfo, actor_name: str, actor_id: Any) -> str:
        first_name = actor_name.split()[0] if actor_name.split() else ''
        lookup = f'{site.base_url.rstrip("/")}/api/v2/search/actors?thumb_size=355x475&query={quote(first_name)}'
        model_page_elements = await self.fetch_json(lookup)
        match = next((x for x in (model_page_elements or {}).get('results', []) if x.get('id') == actor_id), None)
        return (match.get('thumb') or {}).get('image') or '' if match else ''

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.title = self._extra(scene).result.get('title') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.summary = strip_tags(self._extra(scene).result.get('long_description')) or ''

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        extra = self._extra(scene)

        metadata.release_date = iso_date(extra.result.get('release_date') or '') or extra.date_fallback or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        n = self._unique_actor_count(scene)
        if group := self.group_genre_for(n):
            metadata.genres = [group]

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for a in self._extra(scene).result.get('actors', []):
            actor_name = a.get('name')
            if not actor_name or actor_name in seen:
                continue

            seen.add(actor_name)
            photo = (a.get('thumb') or {}).get('image') or ''
            if photo.endswith('noimageavailable.gif'):
                photo = await self._actor_thumb_fallback(scene.site, actor_name, a.get('id')) or photo

            actors.append(ActorResult(name=actor_name, photo_url=photo))

        metadata.actors = actors

    async def fetch_directors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        directors = [ActorResult(name=d['name']) for d in self._extra(scene).result.get('directors', []) if d.get('name')]

        metadata.directors = directors or None

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        image = (self._extra(scene).result.get('thumb') or {}).get('image')

        metadata.art = [image] if image else []
