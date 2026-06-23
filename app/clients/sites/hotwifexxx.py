from __future__ import annotations

import re
from urllib.parse import urlsplit

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date
from app.utils.helpers.html_helpers import first_text
from app.utils.logging.logger import logger
from app.utils.searchengines import SearchOptions, web_search

_DESCRIPTION_RE = re.compile(r'description:\s*', re.IGNORECASE)
_RELEASED_XP = '//div[contains(@class,"released2") and contains(@class,"trailerStarr")]'
_CAST_XP = '//div[contains(@class,"trailerMInfo")]//span[contains(@class,"tour_update_models")]/a'


def _date_of(raw: str) -> str | None:
    seg = raw.split(',')[0].strip()
    return iso_date(seg) if seg else None


class HotwifeXXXClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        host = urlsplit(ctx.site_info.base_url).hostname or ''
        if not host:
            return []
        try:
            found = await web_search(SearchOptions(query=ctx.title, site=host, num=10))
        except Exception as err:  # noqa: BLE001 - search failure is non-fatal
            logger.warn(ctx.site_info.name, f'webSearch threw: {err}')
            return []

        seen: set[str] = set()
        candidates: list[str] = []
        for u in found:
            if '/updates/' in u and '/tour_hwxxx/' in u and u not in seen:
                seen.add(u)
                candidates.append(u)

        results: list[SearchResult] = []
        for scene_url in candidates:
            loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] {scene_url}')
            if not loaded:
                continue
            title = first_text(loaded['sel'], '//div[contains(@class,"trailerInfo")]//h2')
            if not title:
                continue
            date = _date_of(first_text(loaded['sel'], _RELEASED_XP))
            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=ctx.title,
                    display_date=date,
                    search_date=ctx.search_date,
                )
            )
        return results

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//div[contains(@class,"trailerInfo")]//h2') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//div[contains(@class,"dvdDescription")]//p')
        return _DESCRIPTION_RE.sub('', raw, count=1).strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return 'HotwifeXXX'

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return _date_of(first_text(scene.sel, _RELEASED_XP)) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        count = len(scene.sel.xpath(_CAST_XP))
        if count == 3:
            return ['Threesome']
        if count == 4:
            return ['Foursome']
        if count > 4:
            return ['Orgy']
        return []

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        for el in scene.sel.xpath(_CAST_XP):
            name = (el.xpath('normalize-space(.)').get() or '').strip()
            if not name:
                continue
            photo = ''
            href = (el.xpath('@href').get() or '').strip()
            if href:
                actor_url = href if href.startswith('http') else absolute_url(href, scene.site.base_url)
                loaded = await self.fetch_and_load(actor_url, FetchCtx(capture=scene.capture), f'GET {actor_url} (actor)')
                raw = (loaded['sel'].xpath('(//div[contains(@class,"modelBioPic")]//img/@src0_3x)[1]').get() or '').strip() if loaded else ''
                photo = (raw if raw.startswith('http') else absolute_url(raw, scene.site.base_url)) if raw else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        images: list[str] = []
        for raw in scene.sel.xpath('//span[@id="trailer_thumb"]//img/@src').getall():
            raw = (raw or '').strip()
            if not raw:
                continue
            abs_url = raw if raw.startswith('http') else absolute_url(raw, scene.site.base_url)
            if abs_url not in images:
                images.append(abs_url)
        return images
