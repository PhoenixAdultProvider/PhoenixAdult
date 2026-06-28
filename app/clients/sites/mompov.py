from __future__ import annotations

from typing import Any

from parsel import Selector

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_text


def _holder_date(scope: Selector) -> str | None:
    dh = scope.xpath('//div[contains(@class,"date_holder")]')
    if not dh:
        return None
    spans = dh[0].xpath('./span')
    if not spans:
        return None
    month = (spans[0].xpath('normalize-space(.)').get() or '')[:3]
    inner = spans[0].xpath('.//span')
    year = (inner[0].xpath('normalize-space(.)').get() or '').strip() if inner else ''
    day = (spans[1].xpath('normalize-space(.)').get() or '').strip() if len(spans) > 1 else ''
    if month and day and year:
        return iso_date(f'{month} {day} {year}', '%b %d %Y')
    return None


class MomPOVClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = f'{base}{ctx.site_info.search_path.replace("{query}", ctx.encoded)}'
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {url}')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//div[@id="inner_content"]//div[contains(@class,"entry")]'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/div[contains(@class,"title_holder")]//h1//a')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = (source.xpath('(.//div[contains(@class,"title_holder")]//h1//a/@href)[1]').get() or '').strip()
        if not href:
            return ''
        return absolute_url(href, loaded.site.base_url)

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        return _holder_date(source)

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//a[contains(@class,"title")]') or (scene.sel.xpath('//meta[@property="og:title"]/@content').get() or '').strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//div[contains(@class,"entry_content")]//p') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return 'MomPOV'

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return _holder_date(scene.sel) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        return ['MILF']

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        return []

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        first_div = scene.sel.xpath('//div[@id="inner_content"]/div')
        if not first_div:
            return []
        raw = (first_div[0].xpath('(.//a//img/@src)[1]').get() or '').strip()
        if not raw:
            return []
        return [absolute_url(raw, scene.site.base_url)]
