from __future__ import annotations

from urllib.parse import urlsplit

from parsel import Selector

from app.clients.base import Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, slugify
from app.utils.helpers.html_helpers import first_attr
from app.utils.logging.logger import logger
from app.utils.searchengines import SearchOptions, web_search_available, web_search_filtered

STUDIO = 'Evolved Fights Network'
_URL_CONTAINS = '/updates/'
_DATE_FMT = '%m/%d/%Y'


class EvolvedFightsClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        candidates: list[str] = []
        slug = slugify(ctx.title)
        if slug:
            candidates.append(f'{base}/{slug}.html')

        if web_search_available():
            host = urlsplit(ctx.site_info.base_url).netloc
            try:
                for url in await web_search_filtered(SearchOptions(query=ctx.title, site=host, num=10), url_contains=_URL_CONTAINS):
                    if url not in candidates:
                        candidates.append(url)
            except Exception as err:  # noqa: BLE001 - search is best-effort
                logger.debug(ctx.site_info.name, f'webSearch: {err}')

        for url in candidates:
            loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] candidate {url}')
            if not loaded:
                continue
            title = (loaded['sel'].xpath('(//title)[1]').xpath('string(.)').get() or '').strip()
            if not title:
                continue
            raw = (loaded['sel'].xpath('(//span[contains(@class,"update_date")])[1]').xpath('string(.)').get() or '').strip()
            date_iso = iso_date(raw, _DATE_FMT) if raw else None
            results.append(build_search_result(title=title, scene_url=url, query=ctx.title, display_date=date_iso, search_date=ctx.search_date))

    # ── Field hooks ───────────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = (scene.sel.xpath('(//title)[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = (scene.sel.xpath('(//span[contains(@class,"latest_update_description")])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name if scene.site.name != STUDIO else None

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [STUDIO]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//span[contains(@class,"update_date")])[1]').xpath('string(.)').get() or '').strip()
        metadata.release_date = (iso_date(raw, _DATE_FMT) if raw else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        genres = [g for g in (first_attr(a, 'normalize-space(.)') for a in scene.sel.xpath('//span[contains(@class,"tour_update_tags")]//a')) if g]
        metadata.genres = genres or []

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            raw = first_attr(sel, '(//img[contains(@class,"model_bio_thumb")])[1]/@src0_3x')
            return absolute_url(raw, base) if raw else ''

        refs: list[tuple[str, str]] = []
        for a in scene.sel.xpath(
            '//div[contains(@class,"update_block_info") and contains(@class,"model_update_block_info")]//span[contains(@class,"tour_update_models")]//a'
        ):
            name = first_attr(a, 'normalize-space(.)')
            href = first_attr(a, '@href')
            if name:
                refs.append((name, absolute_url(href, base) if href else ''))
        metadata.actors = await self.resolve_actor_photos(refs, extract_photo)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = first_attr(scene.sel, '(//span[contains(@class,"model_update_thumb")]//img)[1]/@src0_4x')
        if not raw:
            return
        poster = absolute_url(raw, scene.site.base_url)
        out = [poster]
        poster2 = poster.replace('0-4x', '1-4x')
        if poster2 != poster:
            out.append(poster2)
        metadata.raw_image_urls = out
