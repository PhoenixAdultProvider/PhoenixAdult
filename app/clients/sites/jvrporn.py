from __future__ import annotations

from urllib.parse import urlsplit

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, pack_cur_id
from app.utils.helpers.html_helpers import first_text
from app.utils.logging.logger import logger
from app.utils.searchengines import SearchOptions, web_search


class JVRPornClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        scene_id = ctx.scene_id
        rest = ctx.title.strip()

        candidates: list[str] = []
        if scene_id:
            candidates.append(f'{base}/video/{scene_id}')
        if rest:
            host = urlsplit(ctx.site_info.base_url).hostname or ''
            try:
                for url in await web_search(SearchOptions(query=rest, site=host, num=10)):
                    if '/video/' in url and url not in candidates:
                        candidates.append(url)
            except Exception as err:  # noqa: BLE001 - search failure is non-fatal
                logger.warn(ctx.site_info.name, f'webSearch threw: {err}')

        results: list[SearchResult] = []
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
        return results

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//h1') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//pre') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return 'JVR Porn'

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return ['JVR Porn']

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        return scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [s.xpath('normalize-space(.)').get() for s in scene.sel.xpath('//td[contains(@class,"tags")]//span')]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        entries = [ActorResult(name=s.xpath('normalize-space(.)').get() or '') for s in scene.sel.xpath('//a[contains(@class,"actress")]//span')]
        return self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        images: list[str] = []

        def push(raw: str) -> None:
            raw = (raw or '').strip()
            if not raw:
                return
            abs_url = absolute_url(raw, scene.site.base_url)
            if abs_url not in images:
                images.append(abs_url)

        for raw in scene.sel.xpath('//div[contains(@id,"snapshot-gallery")]//a/@href').getall():
            push(raw)
        for raw in scene.sel.xpath('//deo-video/@cover-image').getall():
            push(raw)
        return images
