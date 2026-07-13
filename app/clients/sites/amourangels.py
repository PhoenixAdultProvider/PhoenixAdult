from __future__ import annotations

import re

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text

_TITLE_XP = '//td[contains(@class,"blox-bg")]//td[2]//b'
_DATE_CELL_XP = '//td[contains(@class,"blox-bg")]//td[2]'
_VIDEO_PREFIX = re.compile(r'^Video\s*', re.IGNORECASE)


def _strip_video_label(s: str) -> str:
    return _VIDEO_PREFIX.sub('', s).strip()


class AmourAngelsClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        scene_url = base + ctx.site_info.search_path.replace('{query}', ctx.title.strip())
        loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] directScene {scene_url}')
        if not loaded:
            return
        title = _strip_video_label(first_text(loaded['sel'], _TITLE_XP))
        if not title:
            return
        results.append(
            build_search_result(
                title=title,
                scene_url=scene_url,
                query=ctx.title,
                search_date=ctx.search_date,
                score=100,
                search_url=scene_url,
                cur_id=pack_cur_id([scene_url]),
            )
        )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        metadata.title = _strip_video_label(first_text(sel, _TITLE_XP))

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        cell_text = first_text(sel, _DATE_CELL_XP)
        parts = cell_text.split('Added')
        if len(parts) < 2:
            return
        candidate = parts[1].strip()[:10]
        metadata.release_date = iso_date(candidate, '%Y-%m-%d') or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.genres = ['Softcore', 'European Girls']

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for a in sel.xpath('//td[contains(@class,"modinfo")]//a'):
            name = first_attr(a, 'normalize-space(.)')
            href = first_attr(a, '@href')
            if not name or not href:
                continue
            actor_url = absolute_url(href, scene.site.base_url)
            actor_page = await self.fetch_and_load(actor_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {name}')
            photo = ''
            if actor_page:
                raw = (
                    actor_page['sel'].xpath('(//td[contains(@class,"modelinfo-bg")]//td[1]//img/@src)[1]').get()
                    or actor_page['sel'].xpath('(//td[contains(@class,"modelinfo-bg")]//img/@src)[1]').get()
                    or ''
                )
                photo = absolute_url(raw, scene.site.base_url) if raw else ''
            lname = name.lower()
            if lname not in seen:
                seen.add(lname)
                actors.append(ActorResult(name=lname, photo_url=photo, gender='female'))
        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        coll = self.image_collector(lambda raw: absolute_url(raw, scene.site.base_url))
        for el in sel.xpath('//td[contains(@class,"noisebg")]//div//img'):
            coll['push'](first_attr(el, '@src'))
        metadata.art = coll['list']
