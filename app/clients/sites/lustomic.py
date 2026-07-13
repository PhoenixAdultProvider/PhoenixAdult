from __future__ import annotations

from parsel import Selector

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import build_search_result, pack_cur_id
from app.utils.helpers.html_helpers import first_attr


def _sibling_text(sel: Selector, alt: str, tag: str) -> str:
    return (sel.xpath(f'normalize-space((//img[@alt="{alt}"])[1]/following-sibling::{tag}[1])').get() or '').strip()


def _cast_names(sel: Selector) -> list[str]:
    raw = sel.xpath('normalize-space((//p[contains(.,"Starring")]//span)[1])').get() or ''
    return [n.strip() for n in raw.split(';') if n.strip()]


class LustomicClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        scene_url = f'{base}{ctx.site_info.search_path.replace("{query}", ctx.encoded)}'

        loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] sceneID {scene_url}')
        if not loaded:
            return
        title = _sibling_text(loaded['sel'], 'Video Preview', 'p')
        if not title:
            return
        results.append(
            build_search_result(
                title=title,
                scene_url=scene_url,
                query=ctx.title,
                search_date=ctx.search_date,
                cur_id=pack_cur_id([x for x in (scene_url, ctx.search_date) if x]),
            )
        )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = _sibling_text(scene.sel, 'Video Preview', 'p') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = _sibling_text(scene.sel, 'Video Description', 'div') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'Lustomic'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        cast = len(_cast_names(scene.sel))
        if cast == 3:
            metadata.genres = ['Threesome']
        elif cast == 4:
            metadata.genres = ['Foursome']
        elif cast > 4:
            metadata.genres = ['Orgy']

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.actors = [ActorResult(name=name, photo_url='', gender='') for name in _cast_names(scene.sel)]

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.raw_image_urls = self.dedup_strings([first_attr(a, '@href') for a in scene.sel.xpath('//a[contains(@href,"video_preview_images")]')])
