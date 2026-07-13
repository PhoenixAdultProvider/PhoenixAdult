from __future__ import annotations

import json
from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text


class PornstarPlatinumClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//div[contains(@class,"no-nth")]'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def build_search_results(self, source: Any, loaded: LoadedSearch, results: list[SearchResult]) -> None:
        anchor = source.xpath('(.//div[contains(@class,"item-content")]//h3//a)[1]')
        title = first_attr(anchor, 'normalize-space(.)')
        href = first_attr(anchor, '@href')
        if not title or not href:
            return
        scene_url = absolute_url(href, loaded.site.base_url)
        poster = first_attr(source, '(.//div[contains(@class,"item-header")]//a//img/@rel)[1]')
        date = iso_date(first_text(source, './/span[contains(@class,"content-date")]'))
        actor = first_text(source, './/span[contains(@class,"marker") and contains(@class,"left")]')
        packed = json.dumps({'url': scene_url, 'title': title, 'releaseDate': date or '', 'poster': poster, 'actor': actor})
        results.append(
            build_search_result(
                title=title,
                scene_url=scene_url,
                query=loaded.ctx.title,
                display_date=date,
                search_date=loaded.ctx.search_date,
                cur_id=pack_cur_id([packed]),
            )
        )

    # ── Context loader (card fields packed into the curID) ────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        try:
            packed = json.loads(payload)
        except (ValueError, TypeError):
            return None
        loaded = await self.fetch_and_load(
            packed.get('url', ''), FetchCtx(capture=ctx.capture if ctx else None), f'[{site.name}] scene {packed.get("url", "")}'
        )
        if not loaded:
            return None
        return LoadedScene(url=packed.get('url', ''), site=site, capture=ctx.capture if ctx else None, sel=loaded['sel'], html=loaded['html'], extra=packed)

    def _data(self, scene: LoadedScene) -> dict[str, Any]:
        return scene.extra if isinstance(scene.extra, dict) else {}

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.title = (self._data(scene).get('title') or '').strip()

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = first_text(scene.sel, '//div[contains(@class,"panel-content")]//p')

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'Pornstar Platinum'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = (self._data(scene).get('releaseDate') or '') or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//div[contains(@class,"tagcloud")]//a')]
        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        name = (self._data(scene).get('actor') or '').strip()
        metadata.actors = [ActorResult(name=name)] if name else []

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        poster = (self._data(scene).get('poster') or '').strip()
        metadata.raw_image_urls = [poster] if poster else []
