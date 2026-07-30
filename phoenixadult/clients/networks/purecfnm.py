from __future__ import annotations

import json
from typing import Any

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.helpers import build_search_result, iso_date, load_data, pack_cur_id
from phoenixadult.utils.helpers.html_helpers import first_attr

STUDIO = 'PureCFNM'
_GENRES: dict[str, list[str]] = load_data(__file__, 'purecfnm_genres')


class PureCFNMClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        words = search_data.title.strip().split()
        model_id = '-'.join(words[:2])
        scene_title = ' '.join(words[2:])
        if not model_id:
            return

        search_url = base + search_data.site_info.search_path.replace('{query}', model_id)
        search_results = await self.fetch_and_load(search_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {search_url}')
        if not search_results:
            return

        for search_result in search_results['sel'].xpath('//div[contains(@class,"update_block")]'):
            title = (search_result.xpath('(.//span[contains(@class,"update_title")])[1]').xpath('string(.)').get() or '').strip()
            if not title:
                continue

            summary = (search_result.xpath('(.//span[contains(@class,"latest_update_description")])[1]').xpath('string(.)').get() or '').strip()
            raw_date = (search_result.xpath('(.//span[contains(@class,"update_date")])[1]').xpath('string(.)').get() or '').strip()
            date = (iso_date(raw_date) or '') if raw_date else ''
            actors = [n for n in (first_attr(a, 'normalize-space(.)') for a in search_result.xpath('.//span[contains(@class,"tour_update_models")]//a')) if n]
            poster = first_attr(search_result, '(.//div[contains(@class,"update_image")]//a//img)[1]/@src')
            packed = pack_cur_id([json.dumps({'title': title, 'summary': summary, 'release_date': date, 'actors': actors, 'poster': poster})])

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=search_url,
                    query=scene_title or search_data.title,
                    display_date=date or None,
                    search_date=search_data.search_date,
                    cur_id=packed,
                )
            )

    # ── Context Loader — Decode the JSON-Packed Scene; No Detail Fetch ──────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        try:
            scene = json.loads(payload)
        except (ValueError, TypeError):
            return None

        if not isinstance(scene, dict):
            return None

        return LoadedScene(url='', site=site, capture=ctx.capture if ctx else None, sel=None, html='', extra=scene)

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _packed(self, scene: LoadedScene) -> dict[str, Any]:
        return scene.extra or {}

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.title = self._packed(scene).get('title') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.summary = self._packed(scene).get('summary') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        d = self._packed(scene).get('release_date')

        metadata.release_date = (iso_date(d) or d) if d else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        genres = list(_GENRES.get(scene.site.name, ['CFNM']))
        count = len(self._packed(scene).get('actors') or [])
        if count == 2:
            genres.append('Threesome')
        elif count == 3:
            genres.append('Foursome')
        elif count > 3:
            genres.append('Group')

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        entries = [ActorResult(name=n) for n in (self._packed(scene).get('actors') or [])]

        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        poster = self._packed(scene).get('poster')

        metadata.art = [poster] if poster else []
