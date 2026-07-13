from __future__ import annotations

import re
from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr

STUDIO = 'Killergram'
_TITLE_RE = re.compile(r'/models/([\w ]+)/\1_([\w ]+)/')


def _extract_title(sel: Any) -> str:
    src = first_attr(sel, '(//img[@id="episode_001"])[1]/@src')
    m = _TITLE_RE.search(src)
    return m.group(2).strip() if m else ''


def _header_sibling(sel: Any, needle: str) -> str:
    for span in sel.xpath('//span[contains(@class,"episodeheader")]'):
        if needle in (span.xpath('string(.)').get() or '').lower():
            return ''.join(span.xpath('../text()').getall()).strip()
    return ''


class KillergramClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        scene_id = ctx.title.strip().split()[0] if ctx.title.strip() else ''
        if not scene_id:
            return
        base = ctx.site_info.base_url.rstrip('/')
        scene_url = base + ctx.site_info.search_path.replace('{query}', scene_id)
        loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] sceneID {scene_id}')
        if not loaded:
            return
        title = _extract_title(loaded['sel'])
        if not title:
            return
        results.append(
            build_search_result(
                title=title,
                scene_url=scene_url,
                query=ctx.title,
                display_date=iso_date(_header_sibling(loaded['sel'], 'published')),
                search_date=ctx.search_date,
                score=100,
                cur_id=pack_cur_id([scene_id]),
            )
        )

    # ── Context loader (curID is an episode id, not a URL) ──────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        scene_id = payload.split('|')[0]
        url = site.base_url.rstrip('/') + site.search_path.replace('{query}', scene_id)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture if ctx else None), f'[{site.name}] detail {url}')
        if not loaded:
            return None
        return LoadedScene(url=url, site=site, capture=ctx.capture if ctx else None, sel=loaded['sel'], html=loaded['html'])

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = _extract_title(scene.sel) or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = (scene.sel.xpath('(//table[contains(@class,"episodetext")]//tr)[5]//td[2]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.release_date = iso_date(_header_sibling(scene.sel, 'published'))

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.genres = ['British']

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for span in scene.sel.xpath('//span[contains(@class,"episodeheader")]'):
            if 'starring' not in (span.xpath('string(.)').get() or '').lower():
                continue
            for a in span.xpath('../span[contains(@class,"modelstarring")]//a'):
                name = first_attr(a, 'normalize-space(.)')
                if name and name not in seen:
                    seen.add(name)
                    actors.append(ActorResult(name=name))
        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        images: list[str] = []
        n = 1
        while True:
            src = (scene.sel.xpath(f'(//img[@id="episode_{n:03d}"])[1]/@src').get() or '').strip()
            if not src:
                break
            images.append(src)
            n += 1
        metadata.art = images
