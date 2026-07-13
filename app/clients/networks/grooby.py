from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from parsel import Selector

from app.clients.base import Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, strip_query
from app.utils.helpers.html_helpers import first_attr
from app.utils.logging.logger import logger
from app.utils.searchengines import SearchOptions, web_search_available, web_search_filtered

STUDIO = 'Grooby'
_TITLE_XP = '//div[contains(@class,"trailer_videoinfo")]//h3 | //div[contains(@class,"trailer_toptitle_left")]'


def _added_date(sel: Any, scope_xp: str) -> str | None:
    txt = sel.xpath(f'({scope_xp})[1]').xpath('string(.)').get() or ''
    at = txt.find('Added')
    if at < 0:
        return None
    after = txt[at + len('Added') :]
    dash = after.find('-')
    raw = (after[dash + 1 :] if dash >= 0 else after).split('\n')[0].strip()
    return iso_date(raw) if raw else None


class GroobyClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        if not web_search_available():
            return
        host = urlsplit(ctx.site_info.base_url).netloc
        try:
            candidates = [strip_query(u) for u in await web_search_filtered(SearchOptions(query=ctx.title, site=host, num=10), url_contains='/trailers/')]
        except Exception as err:  # noqa: BLE001 - best-effort
            logger.debug(ctx.site_info.name, f'webSearch: {err}')
            return

        seen: set[str] = set()
        for scene_url in candidates:
            if scene_url in seen:
                continue
            seen.add(scene_url)
            loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] candidate {scene_url}')
            if not loaded:
                continue
            title = (loaded['sel'].xpath(f'({_TITLE_XP})[1]').xpath('string(.)').get() or '').strip()
            if not title:
                continue
            date_iso = _added_date(loaded['sel'], '//div[contains(@class,"setdesc")]') or _added_date(
                loaded['sel'], '//div[contains(@class,"trailer_videoinfo")]'
            )
            results.append(build_search_result(title=title, scene_url=scene_url, query=ctx.title, display_date=date_iso, search_date=ctx.search_date))

    # ── Field hooks ───────────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        metadata.title = (sel.xpath(f'({_TITLE_XP})[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        ps = sel.xpath('//div[contains(@class,"trailer_videoinfo")]//p | //div[contains(@class,"trailerpage_info")]//p[not(@class)]')
        if not ps:
            return
        metadata.summary = (ps[-1].xpath('string(.)').get() or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        metadata.release_date = (
            _added_date(sel, '//div[contains(@class,"setdesc")]') or _added_date(sel, '//div[contains(@class,"trailer_videoinfo")]') or scene.scene_date or None
        )

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            raw = (
                sel.xpath('(//div[contains(@class,"model_photo")]//img[@id])[1]/@src0_1x').get()
                or sel.xpath('(//div[contains(@class,"model_photo")]//img)[1]/@src').get()
                or ''
            ).strip()
            return absolute_url(raw, base) if raw else ''

        refs: list[tuple[str, str]] = []
        for el in sel.xpath(
            '//div[contains(@class,"trailer_videoinfo")]//p[contains(.,"Featuring")]//a | //div[contains(@class,"setdesc")]//a[contains(@href,"/models/")]'
        ):
            name = first_attr(el, 'normalize-space(.)')
            href = first_attr(el, '@href')
            if name and href:
                refs.append((name, absolute_url(href, base)))
        metadata.actors = await self.resolve_actor_photos(refs, extract_photo)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        coll = self.image_collector(lambda raw: absolute_url(raw, scene.site.base_url))
        xpaths = (
            '//div[contains(@class,"trailerpage_photoblock_fullsize")]//a/@href',
            '//div[contains(@class,"trailerposter")]//img/@src0_4x',
            '//div[contains(@class,"player-thumb")]//img/@src0_4x',
        )
        for xpath in xpaths:
            for raw in sel.xpath(xpath).getall():
                coll['push'](raw)
        images: list[str] = coll['list']
        metadata.art = images or []
