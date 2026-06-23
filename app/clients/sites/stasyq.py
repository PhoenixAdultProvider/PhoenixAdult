from __future__ import annotations

import re

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import build_search_result, pack_cur_id
from app.utils.helpers.html_helpers import first_text

STUDIO = 'StasyQ'
_COOKIE = {'Cookie': 'lang=en'}
_DIGITS_RE = re.compile(r'^\d+$')


class StasyQClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        tokens = (ctx.full_title or ctx.title).split()
        scene_id = next((t for t in tokens if _DIGITS_RE.match(t)), None)
        if not scene_id:
            return []
        base = ctx.site_info.base_url.rstrip('/')
        scene_url = base + ctx.site_info.search_path.replace('{query}', scene_id)
        loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture, headers=_COOKIE), f'[{ctx.site_info.name}] sceneID {scene_id}')
        if not loaded:
            return []
        title = first_text(loaded['sel'], '//h1')
        if not title:
            return []
        return [build_search_result(title=title, scene_url=scene_url, query=ctx.title, search_date=ctx.search_date, score=100, cur_id=pack_cur_id([scene_url]))]

    # ── Context loader ────────────────────────────────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        url, _, tail = payload.partition('|')
        scene_date = tail.strip() or None
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture if ctx else None, headers=_COOKIE), f'[{site.name}] detail {url}')
        if not loaded:
            return None
        return LoadedScene(url=url, site=site, scene_date=scene_date, capture=ctx.capture if ctx else None, sel=loaded['sel'], html=loaded['html'])

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//h1') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//div[contains(@class,"about-section__text")]/p') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [STUDIO]

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [
            a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//section[contains(@class,"about-section")]//div[contains(@class,"tags")]//a')
        ]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in scene.sel.xpath('//section[contains(@class,"content-section")]//div[contains(@class,"release-card__model")]//a'):
            name = (el.xpath('normalize-space(.)').get() or '').strip()
            if name and name not in seen:
                seen.add(name)
                actors.append(ActorResult(name=name))
        return actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        out: list[str] = []
        for href in scene.sel.xpath('//div[contains(@class,"js-release-gallery")]//a/@href').getall():
            h = (href or '').strip()
            if h and h not in out:
                out.append(h)
        return out
