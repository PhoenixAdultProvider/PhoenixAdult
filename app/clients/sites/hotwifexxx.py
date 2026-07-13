from __future__ import annotations

import re
from urllib.parse import urlsplit

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date
from app.utils.helpers.html_helpers import first_attr, first_text
from app.utils.logging.logger import logger
from app.utils.searchengines import SearchOptions, web_search

_DESCRIPTION_RE = re.compile(r'description:\s*', re.IGNORECASE)
_RELEASED_XP = '//div[contains(@class,"released2") and contains(@class,"trailerStarr")]'
_CAST_XP = '//div[contains(@class,"trailerMInfo")]//span[contains(@class,"tour_update_models")]/a'


def _date_of(raw: str) -> str | None:
    seg = raw.split(',')[0].strip()
    return iso_date(seg) if seg else None


class HotwifeXXXClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        host = urlsplit(ctx.site_info.base_url).hostname or ''
        if not host:
            return
        try:
            found = await web_search(SearchOptions(query=ctx.title, site=host, num=10))
        except Exception as err:  # noqa: BLE001 - search failure is non-fatal
            logger.warn(ctx.site_info.name, f'webSearch threw: {err}')
            return

        seen: set[str] = set()
        candidates: list[str] = []
        for u in found:
            if '/updates/' in u and '/tour_hwxxx/' in u and u not in seen:
                seen.add(u)
                candidates.append(u)

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

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = first_text(scene.sel, '//div[contains(@class,"trailerInfo")]//h2') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//div[contains(@class,"dvdDescription")]//p')
        metadata.summary = _DESCRIPTION_RE.sub('', raw, count=1).strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'HotwifeXXX'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.release_date = _date_of(first_text(scene.sel, _RELEASED_XP)) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        count = len(scene.sel.xpath(_CAST_XP))
        if group := self.group_genre_for(count):
            metadata.genres = [group]

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        for el in scene.sel.xpath(_CAST_XP):
            name = first_attr(el, 'normalize-space(.)')
            if not name:
                continue
            photo = ''
            href = first_attr(el, '@href')
            if href:
                actor_url = absolute_url(href, scene.site.base_url)
                loaded = await self.fetch_and_load(actor_url, FetchCtx(capture=scene.capture), f'GET {actor_url} (actor)')
                raw = first_attr(loaded['sel'], '(//div[contains(@class,"modelBioPic")]//img/@src0_3x)[1]') if loaded else ''
                photo = (absolute_url(raw, scene.site.base_url)) if raw else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        coll = self.image_collector(lambda raw: absolute_url(raw, scene.site.base_url))
        for raw in scene.sel.xpath('//span[@id="trailer_thumb"]//img/@src').getall():
            coll['push']((raw or '').strip())
        metadata.raw_image_urls = coll['list']
