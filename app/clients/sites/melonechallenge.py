from __future__ import annotations

from urllib.parse import urlsplit

from app.clients.base import Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text
from app.utils.logging.logger import logger
from app.utils.searchengines import SearchOptions, web_search


class MeloneChallengeClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        host = urlsplit(ctx.site_info.base_url).netloc
        try:
            found = await web_search(SearchOptions(query=ctx.title, site=host, num=10))
        except Exception as err:  # noqa: BLE001 - search failure is non-fatal
            logger.warn(self.tag(ctx.site_info), f'webSearch threw: {err}')
            return []
        candidates = list(dict.fromkeys(u for u in found if '/video/' in u))

        results: list[SearchResult] = []
        for scene_url in candidates:
            loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] {scene_url}')
            if not loaded:
                continue
            title = first_text(loaded['sel'], '//a[contains(@class,"dark")]')
            if not title:
                continue
            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=ctx.title,
                    search_date=ctx.search_date,
                    cur_id=pack_cur_id([x for x in (scene_url, ctx.search_date) if x]),
                )
            )
        return results

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//a[contains(@class,"dark")]') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return 'Melone Challenge'

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        return scene.scene_date or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        images: list[str] = []
        for el in scene.sel.xpath('//figure//img'):
            raw = first_attr(el, '@src')
            if not raw:
                continue
            abs_url = absolute_url(raw, scene.site.base_url)
            if abs_url not in images:
                images.append(abs_url)
        return images
