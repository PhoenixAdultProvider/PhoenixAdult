from __future__ import annotations

import re

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_text
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result

STUDIO = 'Vivid Entertainment'
_ENDPOINTS = ('videos', 'dvds')
_RELEASED_RE = re.compile(r'Released:', re.IGNORECASE)


class VividClient(Client):
    title_xpath = '//h2[contains(@class,"scene-h2-heading")]'
    summary_xpath = '//p[contains(@class,"indie-model-p")]'
    genres_xpath = '//h5[contains(.,"Categories:")]//a'

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        seen: set[str] = set()
        for scene_type in _ENDPOINTS:
            api_url = f'{base}/{scene_type}/api/?flagType=video&search={search_data.encoded}'
            search_results = await self.fetch_json(api_url, FetchCtx(capture=search_data.capture), label=f'[{search_data.site_info.name}] search {scene_type}')
            if not isinstance(search_results, dict):
                continue

            for hit in search_results.get('responseData') or []:
                scene_url = (hit.get('url') or '').strip()
                title = (hit.get('name') or '').strip()
                if not scene_url or not title or scene_url in seen:
                    continue

                seen.add(scene_url)
                date = iso_date(hit['release_date']) if hit.get('release_date') else None
                real_sub = ((hit.get('site') or {}).get('name') or '').strip()
                sub_site = real_sub or 'DVD'
                poster = hit.get('placard_800') or ''

                results.append(
                    build_search_result(
                        site=search_data.site_info,
                        title=title,
                        scene_url=scene_url,
                        query=search_data.title,
                        display_date=date,
                        search_date=search_data.search_date,
                        cur_id=pack_cur_id([scene_url, date or '', sub_site, poster]),
                        subsite=real_sub or None,
                    )
                )

    # ── Context Loader: unpack subsite + poster ───────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        parts = payload.split('|')
        url = parts[0]
        date = (parts[1] if len(parts) > 1 else '').strip()
        sub_site = (parts[2] if len(parts) > 2 else '').strip() or site.name
        poster_url = (parts[3] if len(parts) > 3 else '').strip()
        details_page_elements = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture if ctx else None), f'[{site.name}] detail {url}')
        if not details_page_elements:
            return None

        return LoadedScene(
            url=url,
            site=site,
            scene_date=date or None,
            capture=ctx.capture if ctx else None,
            sel=details_page_elements['sel'],
            html=details_page_elements['html'],
            extra={'sub_site': sub_site, 'poster_url': poster_url},
        )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _sub_site(self, scene: LoadedScene) -> str:
        if isinstance(scene.extra, dict):
            return scene.extra.get('sub_site') or scene.site.name

        return scene.site.name

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._sub_site(scene)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [self._sub_site(scene)]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = _RELEASED_RE.sub('', first_text(details_page_elements, '//h5[contains(.,"Released:")]')).strip()
        if date:
            parsed = iso_date(date, '%b %d, %Y') or iso_date(date)
            if parsed:
                metadata.release_date = parsed
                return

        if scene.scene_date:
            metadata.release_date = iso_date(scene.scene_date) or scene.scene_date

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        entries = [
            ActorResult(name=(actor_link.xpath('normalize-space(.)').get() or ''))
            for actor_link in details_page_elements.xpath('//h4[contains(.,"Starring:")]//a')
        ]

        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        poster = scene.extra.get('poster_url') if isinstance(scene.extra, dict) else ''

        metadata.art = [poster] if poster else []
