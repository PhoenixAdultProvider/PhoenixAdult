from __future__ import annotations

from urllib.parse import urlsplit

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, css_bg_image, iso_date, slugify
from app.utils.helpers.html_helpers import first_text
from app.utils.logging.logger import logger
from app.utils.searchengines import SearchOptions, web_search

_DATE_XP = (
    '//span[contains(@class,"date-display-single")]'
    ' | //span[contains(@class,"u-inline-block") and contains(@class,"u-mr--nine")]'
    ' | //div[contains(@class,"video-meta-date")]'
    ' | //div[contains(@class,"date")]'
)


class LustRealityClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        candidates = [f'{base}{ctx.site_info.search_path}{slugify(ctx.title)}']
        host = urlsplit(ctx.site_info.base_url).hostname or ''
        try:
            for url in await web_search(SearchOptions(query=ctx.title, site=host, num=10)):
                if '/scene/' in url and url not in candidates:
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
            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=ctx.title,
                    display_date=iso_date(first_text(loaded['sel'], _DATE_XP)),
                    search_date=ctx.search_date,
                )
            )
        return results

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//h1') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//div[contains(@class,"u-mb--six")]') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return iso_date(first_text(scene.sel, _DATE_XP)) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//a[contains(@href,"/list/category/")]')]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in scene.sel.xpath('//a[contains(@href,"/pornstars/model/")]'):
            name = (el.xpath('normalize-space(.)').get() or '').strip()
            if not name or name in seen:
                continue
            seen.add(name)
            photo = ''
            href = (el.xpath('@href').get() or '').strip()
            if href:
                loaded = await self.fetch_and_load(absolute_url(href, scene.site.base_url), FetchCtx(capture=scene.capture), f'GET {href} (actor)')
                raw = (loaded['sel'].xpath('(//div[contains(@class,"u-ratio--model-poster")]//img/@data-src)[1]').get() or '').strip() if loaded else ''
                photo = (raw if raw.startswith('http') else absolute_url(raw, scene.site.base_url)) if raw else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        images: list[str] = []

        def push(raw: str) -> None:
            raw = (raw or '').strip()
            if not raw:
                return
            abs_url = raw if raw.startswith('http') else absolute_url(raw, scene.site.base_url)
            if abs_url not in images:
                images.append(abs_url)

        for el in scene.sel.xpath('//div[contains(@class,"splash-screen")]'):
            push(css_bg_image(el.xpath('@style').get()))
        for href in scene.sel.xpath('//a[contains(@class,"u-ratio--lightbox")]/@href').getall():
            push(href)
        return images
