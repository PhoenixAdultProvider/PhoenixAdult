from __future__ import annotations

import json
from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import build_search_result, iso_date, load_site_json, pack_cur_id
from app.utils.helpers.html_helpers import first_attr

STUDIO = 'PureCFNM'
_GENRES: dict[str, list[str]] = load_site_json(__file__, 'purecfnm_genres')


class PureCFNMClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        words = ctx.title.strip().split()
        model_id = '-'.join(words[:2])
        scene_title = ' '.join(words[2:])
        if not model_id:
            return []

        search_url = base + ctx.site_info.search_path.replace('{query}', model_id)
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {search_url}')
        if not loaded:
            return []

        results: list[SearchResult] = []
        for block in loaded['sel'].xpath('//div[contains(@class,"update_block")]'):
            title = (block.xpath('(.//span[contains(@class,"update_title")])[1]').xpath('string(.)').get() or '').strip()
            if not title:
                continue
            summary = (block.xpath('(.//span[contains(@class,"latest_update_description")])[1]').xpath('string(.)').get() or '').strip()
            raw_date = (block.xpath('(.//span[contains(@class,"update_date")])[1]').xpath('string(.)').get() or '').strip()
            date = (iso_date(raw_date) or '') if raw_date else ''
            actors = [n for n in (first_attr(a, 'normalize-space(.)') for a in block.xpath('.//span[contains(@class,"tour_update_models")]//a')) if n]
            poster = first_attr(block, '(.//div[contains(@class,"update_image")]//a//img)[1]/@src')
            packed = pack_cur_id([json.dumps({'title': title, 'summary': summary, 'release_date': date, 'actors': actors, 'poster': poster})])
            results.append(
                build_search_result(
                    title=title, scene_url=search_url, query=scene_title or ctx.title, display_date=date or None, search_date=ctx.search_date, cur_id=packed
                )
            )
        return results

    # ── Context loader — decode the JSON-packed scene; no detail fetch ──────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        try:
            scene = json.loads(payload)
        except (ValueError, TypeError):
            return None
        if not isinstance(scene, dict):
            return None
        return LoadedScene(url='', site=site, capture=ctx.capture if ctx else None, sel=None, html='', extra=scene)

    def _packed(self, scene: LoadedScene) -> dict[str, Any]:
        return scene.extra or {}

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        return self._packed(scene).get('title') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        return self._packed(scene).get('summary') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        d = self._packed(scene).get('release_date')
        return (iso_date(d) or d) if d else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        genres = list(_GENRES.get(scene.site.name, ['CFNM']))
        count = len(self._packed(scene).get('actors') or [])
        if count == 2:
            genres.append('Threesome')
        elif count == 3:
            genres.append('Foursome')
        elif count > 3:
            genres.append('Group')
        return genres or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        entries = [ActorResult(name=n) for n in (self._packed(scene).get('actors') or [])]
        return self.dedup_people(entries) or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        poster = self._packed(scene).get('poster')
        return [poster] if poster else None
