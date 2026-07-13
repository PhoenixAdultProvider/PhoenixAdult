from __future__ import annotations

import re

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_text

STUDIO = 'Vivid Entertainment'
_ENDPOINTS = ('videos', 'dvds')
_RELEASED_RE = re.compile(r'Released:', re.IGNORECASE)


class VividClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        seen: set[str] = set()
        for scene_type in _ENDPOINTS:
            api_url = f'{base}/{scene_type}/api/?flagType=video&search={ctx.encoded}'
            payload = await self.fetch_json(api_url, FetchCtx(capture=ctx.capture), label=f'[{ctx.site_info.name}] search {scene_type}')
            if not isinstance(payload, dict):
                continue
            for hit in payload.get('responseData') or []:
                scene_url = (hit.get('url') or '').strip()
                title = (hit.get('name') or '').strip()
                if not scene_url or not title or scene_url in seen:
                    continue
                seen.add(scene_url)
                date = iso_date(hit['release_date']) if hit.get('release_date') else None
                real_sub = ((hit.get('site') or {}).get('name') or '').strip()
                sub_site = real_sub or 'DVD'  # 'DVD' sentinel packs into cur_id; not a display sub-site
                poster = hit.get('placard_800') or ''
                results.append(
                    build_search_result(
                        title=title,
                        scene_url=scene_url,
                        query=ctx.title,
                        display_date=date,
                        search_date=ctx.search_date,
                        cur_id=pack_cur_id([scene_url, date or '', sub_site, poster]),
                        subsite=real_sub or None,
                    )
                )

    # ── Context loader: unpack subsite + poster ───────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        parts = payload.split('|')
        url = parts[0]
        date = (parts[1] if len(parts) > 1 else '').strip()
        sub_site = (parts[2] if len(parts) > 2 else '').strip() or site.name
        poster_url = (parts[3] if len(parts) > 3 else '').strip()
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture if ctx else None), f'[{site.name}] detail {url}')
        if not loaded:
            return None
        return LoadedScene(
            url=url,
            site=site,
            scene_date=date or None,
            capture=ctx.capture if ctx else None,
            sel=loaded['sel'],
            html=loaded['html'],
            extra={'sub_site': sub_site, 'poster_url': poster_url},
        )

    def _sub_site(self, scene: LoadedScene) -> str:
        if isinstance(scene.extra, dict):
            return scene.extra.get('sub_site') or scene.site.name
        return scene.site.name

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = first_text(scene.sel, '//h2[contains(@class,"scene-h2-heading")]') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = first_text(scene.sel, '//p[contains(@class,"indie-model-p")]') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._sub_site(scene)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [self._sub_site(scene)]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = _RELEASED_RE.sub('', first_text(scene.sel, '//h5[contains(.,"Released:")]')).strip()
        if raw:
            parsed = iso_date(raw, '%b %d, %Y') or iso_date(raw)
            if parsed:
                metadata.release_date = parsed
                return
        if scene.scene_date:
            metadata.release_date = iso_date(scene.scene_date) or scene.scene_date

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//h5[contains(.,"Categories:")]//a')]
        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        entries = [ActorResult(name=(a.xpath('normalize-space(.)').get() or '')) for a in scene.sel.xpath('//h4[contains(.,"Starring:")]//a')]
        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        poster = scene.extra.get('poster_url') if isinstance(scene.extra, dict) else ''
        metadata.raw_image_urls = [poster] if poster else []
