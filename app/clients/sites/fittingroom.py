from __future__ import annotations

import re

from parsel import Selector

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import build_search_result, iso_date, load_site_json, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text, meta_content

_COLLECTIONS: dict[str, str] = load_site_json(__file__, 'fittingroom_collections')

STUDIO = 'Fitting-Room'
_SCENE_ID_RE = re.compile(r'/(\d+)/1$')


def _extract_title(sel: Selector) -> str:
    raw = first_text(sel, '//title')
    if not raw:
        return ''
    if '|' in raw:
        parts = raw.split('|')
        return parts[1].strip() if len(parts) > 1 else raw
    return raw


class FittingRoomClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        scene_id = ctx.title.strip().split()[0] if ctx.title.strip() else ''
        if not scene_id:
            return
        scene_url = f'{ctx.site_info.base_url}{ctx.site_info.search_path}{scene_id}/1'
        loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] sceneID {scene_id}')
        if not loaded:
            return
        title = _extract_title(loaded['sel'])
        if not title:
            return
        date = meta_content(loaded['sel'], 'video:release_date')
        results.append(
            build_search_result(
                title=title,
                scene_url=scene_url,
                query=ctx.title,
                display_date=(iso_date(date) if date else None),
                search_date=ctx.search_date,
                score=90,
                search_url=scene_url,
                cur_id=pack_cur_id([scene_url]),
            )
        )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = _extract_title(scene.sel) or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = first_text(scene.sel, '//div/div[contains(.,"Description")]/em') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        collection = first_text(scene.sel, '//div/div[contains(.,"Series")]/a')
        if not collection:
            collection = _COLLECTIONS.get(_extract_title(scene.sel), '')
        metadata.collections = [STUDIO, collection] if collection else [STUDIO]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        date = meta_content(scene.sel, 'video:release_date')
        metadata.release_date = iso_date(date) if date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        actor_name = first_attr(scene.sel, '(//a[contains(@class,"model")]//img/@alt)[1]')
        genres: list[str] = []
        for raw in scene.sel.xpath('//meta[@property="video:tag"]/@content').getall():
            raw = (raw or '').strip()
            cleaned = (raw.replace(actor_name, '').strip() if actor_name else raw).lower()
            if cleaned and cleaned not in genres:
                genres.append(cleaned)
        if 'Fitting Room' not in genres:
            genres.append('Fitting Room')
        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in scene.sel.xpath('//div/div[contains(.,"Models")]/a'):
            name = (el.xpath('normalize-space(.)').get() or '').strip()
            key = name.lower()
            if not name or key in seen:
                continue
            seen.add(key)
            actors.append(ActorResult(name=name))
        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        m = _SCENE_ID_RE.search(scene.url)
        if not m:
            return
        scene_id = m.group(1)
        images = [f'https://www.fitting-room.com/contents/videos_screenshots/0/{scene_id}/preview.jpg']
        for n in range(2, 6):
            images.append(f'https://www.fitting-room.com/contents/videos_screenshots/0/{scene_id}/3840x1400/{n}.jpg')
        metadata.raw_image_urls = images
