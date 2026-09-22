from __future__ import annotations

import json

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.data_files import load_data
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result

STUDIO = 'PureCFNM'
_GENRES: dict[str, list[str]] = load_data(__file__, 'purecfnm_genres')


class PureCFNMClient(Client):
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

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.title = scene.extra_or(dict, {}).get('title') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.summary = scene.extra_or(dict, {}).get('summary') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        d = scene.extra_or(dict, {}).get('release_date')

        metadata.release_date = (iso_date(d) or d) if d else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        genres = list(_GENRES.get(scene.site.name, ['CFNM']))
        count = len(scene.extra_or(dict, {}).get('actors') or [])
        if count == 2:
            genres.append('Threesome')
        elif count == 3:
            genres.append('Foursome')
        elif count > 3:
            genres.append('Group')

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        entries = [ActorResult(name=n) for n in (scene.extra_or(dict, {}).get('actors') or [])]

        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        poster = scene.extra_or(dict, {}).get('poster')

        metadata.art = [poster] if poster else []
