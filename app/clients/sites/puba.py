from __future__ import annotations

from urllib.parse import urlsplit

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, css_bg_image, pack_cur_id
from app.utils.helpers.html_helpers import first_text
from app.utils.logging.logger import logger
from app.utils.searchengines import SearchOptions, web_search

_TITLE_XP = '//div[@id="body-player-container"]//div//div[contains(@class,"tour-video-title")]'


class PubaClient(Client):
    def __init__(self) -> None:
        super().__init__({'Referer': 'https://www.puba.com/pornstarnetwork/index.php', 'Cookie': 'PHPSESSID=rvo9ieo5bhoh81knnmu88c3lf3'})

    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        stem = f'{base}{ctx.site_info.search_path}'

        candidates: list[str] = []
        if ctx.scene_id:
            candidates.append(f'{stem}show_video.php?galid={ctx.scene_id}')
        host = urlsplit(ctx.site_info.base_url).hostname or ''
        try:
            for url in await web_search(SearchOptions(query=ctx.title, site=host, num=10)):
                if 'show_video' in url and 'index' not in url and url not in candidates:
                    candidates.append(url)
        except Exception as err:  # noqa: BLE001 - search failure is non-fatal
            logger.warn(ctx.site_info.name, f'webSearch threw: {err}')

        results: list[SearchResult] = []
        for scene_url in candidates:
            loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] {scene_url}')
            if not loaded:
                continue
            card_title = first_text(loaded['sel'], _TITLE_XP)
            if not card_title:
                continue
            results.append(
                build_search_result(title=card_title, scene_url=scene_url, query=ctx.title, search_date=ctx.search_date, cur_id=pack_cur_id([scene_url]))
            )
        return results

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, _TITLE_XP) or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//center//div//a[contains(@class,"btn-outline-secondary")]')]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        entries = [ActorResult(name=a.xpath('normalize-space(.)').get() or '') for a in scene.sel.xpath('//center//div//a[contains(@class,"btn-secondary")]')]
        return self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        style = scene.sel.xpath('(//div[@id="body-player-container"]/div/a/img/@style)[1]').get() or ''
        bg = css_bg_image(style)
        if not bg:
            return []
        return [bg if bg.startswith('http') else absolute_url(bg, scene.site.base_url)]
