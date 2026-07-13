from __future__ import annotations

from typing import Any
from urllib.parse import quote

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import build_search_result, epoch_date, pack_cur_id
from app.utils.helpers.html_helpers import strip_tags


class UnzipVRClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        data = await self.fetch_json(f'{base}/api/content/v1/search/{quote(ctx.title)}', FetchCtx(capture=ctx.capture))
        videos = (data.get('data') or {}).get('videos') or [] if isinstance(data, dict) else []

        for v in videos:
            title = (v.get('title') or '').strip()
            slug = v.get('slug')
            if not title or not slug:
                continue
            results.append(build_search_result(title=title, scene_url=slug, query=ctx.title, search_date=ctx.search_date, cur_id=pack_cur_id([slug])))

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        base = site.base_url.rstrip('/')
        data = await self.fetch_json(f'{base}/api/content/v1/videos/{payload}', FetchCtx(capture=ctx.capture if ctx else None))
        item = (data.get('data') or {}).get('item') if isinstance(data, dict) else None
        if not isinstance(item, dict):
            return None
        return LoadedScene(url=f'{base}/api/content/v1/videos/{payload}', site=site, capture=ctx.capture if ctx else None, sel=None, html='', extra=item)

    def _item(self, scene: LoadedScene) -> dict[str, Any]:
        return scene.extra or {}

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.title = (self._item(scene).get('title') or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.summary = strip_tags(self._item(scene).get('description')) or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'Unzip VR'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = epoch_date(self._item(scene).get('publishedAt'))

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        genres = [(c.get('name') or '').strip() for c in (self._item(scene).get('categories') or [])]
        metadata.genres = [g for g in genres if g] or []

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        base = scene.site.base_url.rstrip('/')
        actors: list[ActorResult] = []
        for m in self._item(scene).get('models') or []:
            name = (m.get('title') or '').strip()
            if not name:
                continue
            permalink = (m.get('featuredImage') or {}).get('permalink')
            if not permalink and m.get('slug'):
                page = await self.fetch_json(f'{base}/api/content/v1/models/{m["slug"]}', FetchCtx(capture=scene.capture))
                permalink = (((page.get('data') or {}).get('item') or {}).get('featuredImage') or {}).get('permalink') if isinstance(page, dict) else None
            photo = f'{base}{permalink}' if permalink else ''
            actors.append(ActorResult(name=name, photo_url=photo, gender='female'))
        metadata.actors = actors or []

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        item = self._item(scene)
        base = scene.site.base_url.rstrip('/')
        coll = self.image_collector(lambda raw: raw if raw.startswith('http') else f'{base}{raw}')
        for key in ('sliderImage', 'poster'):
            node = item.get(key) or {}
            coll['push'](node.get('permalink'))
        for img in item.get('galleryImages') or []:
            coll['push'](img.get('permalink'))
        images: list[str] = coll['list']
        metadata.art = images or []
