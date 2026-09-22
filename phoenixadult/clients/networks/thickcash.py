from __future__ import annotations

import json

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.data_files import load_data
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result

STUDIO = 'Thick Cash'
_GENRES: dict[str, list[str]] = load_data(__file__, 'thickcash_genres')


class ThickCashClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        words = search_data.title.strip().split()
        model_id = '-'.join(words[:2])
        scene_title = ' '.join(words[2:])
        if not model_id:
            return

        search_url = search_data.search_url(model_id)
        search_results = await self.fetch_and_load(search_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {search_url}')
        if not search_results:
            return

        for search_result in search_results['sel'].xpath('//div[contains(@class,"updateBlock") and contains(@class,"clear")]'):
            title = (search_result.xpath('(.//h3)[1]').xpath('string(.)').get() or '').strip()
            if not title:
                continue

            summary = (search_result.xpath('(.//p)[1]').xpath('string(.)').get() or '').strip()
            raw_date = (search_result.xpath('(.//h4)[1]').xpath('string(.)').get() or '').split(':')[-1].strip()
            date = (iso_date(raw_date) or '') if raw_date else ''
            poster = first_attr(search_result, '(.//*[@src])[1]/@src')
            packed = pack_cur_id([json.dumps({'title': title, 'summary': summary, 'release_date': date or search_data.search_date, 'poster': poster})])

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

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.title = scene.extra_or(dict, {}).get('title') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.summary = scene.extra_or(dict, {}).get('summary') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        d = scene.extra_or(dict, {}).get('release_date')

        metadata.release_date = (iso_date(d) or d) if d else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.genres = list(_GENRES.get(scene.site.name, []))

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        poster = scene.extra_or(dict, {}).get('poster')

        metadata.art = [poster] if poster else []
