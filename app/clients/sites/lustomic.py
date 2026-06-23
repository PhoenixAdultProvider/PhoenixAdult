from __future__ import annotations

from parsel import Selector

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import build_search_result, pack_cur_id


def _sibling_text(sel: Selector, alt: str, tag: str) -> str:
    return (sel.xpath(f'normalize-space((//img[@alt="{alt}"])[1]/following-sibling::{tag}[1])').get() or '').strip()


def _cast_names(sel: Selector) -> list[str]:
    raw = sel.xpath('normalize-space((//p[contains(.,"Starring")]//span)[1])').get() or ''
    return [n.strip() for n in raw.split(';') if n.strip()]


class LustomicClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        scene_url = f'{base}{ctx.site_info.search_path.replace("{query}", ctx.encoded)}'

        loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] sceneID {scene_url}')
        if not loaded:
            return []
        title = _sibling_text(loaded['sel'], 'Video Preview', 'p')
        if not title:
            return []
        return [
            build_search_result(
                title=title,
                scene_url=scene_url,
                query=ctx.title,
                search_date=ctx.search_date,
                cur_id=pack_cur_id([x for x in (scene_url, ctx.search_date) if x]),
            )
        ]

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return _sibling_text(scene.sel, 'Video Preview', 'p') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return _sibling_text(scene.sel, 'Video Description', 'div') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return 'Lustomic'

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        return scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        cast = len(_cast_names(scene.sel))
        if cast == 3:
            return ['Threesome']
        if cast == 4:
            return ['Foursome']
        if cast > 4:
            return ['Orgy']
        return []

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        return [ActorResult(name=name, photo_url='', gender='') for name in _cast_names(scene.sel)]

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        images: list[str] = []
        for a in scene.sel.xpath('//a[contains(@href,"video_preview_images")]'):
            href = (a.xpath('@href').get() or '').strip()
            if href and href not in images:
                images.append(href)
        return images
