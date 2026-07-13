from __future__ import annotations

from urllib.parse import urlsplit

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, pack_cur_id
from app.utils.helpers.html_helpers import first_text
from app.utils.logging.best_effort import best_effort
from app.utils.searchengines import SearchOptions, web_search


class JVRPornClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        scene_id = ctx.scene_id
        rest = ctx.title.strip()

        candidates: list[str] = []
        if scene_id:
            candidates.append(f'{base}/video/{scene_id}')
        if rest:
            host = urlsplit(ctx.site_info.base_url).hostname or ''
            with best_effort(ctx.site_info.name, 'webSearch'):
                for url in await web_search(SearchOptions(query=rest, site=host, num=10)):
                    if '/video/' in url and url not in candidates:
                        candidates.append(url)

        for scene_url in candidates:
            loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] {scene_url}')
            if not loaded:
                continue
            title = first_text(loaded['sel'], '//h1')
            if not title:
                continue
            is_direct = scene_id is not None and scene_id in scene_url
            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=rest or ctx.title,
                    search_date=ctx.search_date,
                    score=100 if is_direct else None,
                    cur_id=pack_cur_id([x for x in (scene_url, ctx.search_date) if x]),
                )
            )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = first_text(scene.sel, '//h1') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = first_text(scene.sel, '//pre') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'JVR Porn'

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = ['JVR Porn']

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        values: list[str | None] = [s.xpath('normalize-space(.)').get() for s in scene.sel.xpath('//td[contains(@class,"tags")]//span')]
        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        entries = [ActorResult(name=s.xpath('normalize-space(.)').get() or '') for s in scene.sel.xpath('//a[contains(@class,"actress")]//span')]
        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        coll = self.image_collector(lambda raw: absolute_url(raw.strip(), scene.site.base_url))
        for raw in scene.sel.xpath('//div[contains(@id,"snapshot-gallery")]//a/@href').getall():
            coll['push'](raw)
        for raw in scene.sel.xpath('//deo-video/@cover-image').getall():
            coll['push'](raw)
        metadata.raw_image_urls = coll['list']
