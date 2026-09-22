from __future__ import annotations

from typing import Any
from urllib.parse import quote

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.data18 import mapping_slug
from phoenixadult.utils.helpers.dates import epoch_date
from phoenixadult.utils.helpers.html_helpers import strip_tags
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result

_DATA18_PROVIDERS = ['VR Bangers', 'VR Conk']


class UnzipVRClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        search_results = await self.fetch_json(f'{base}/api/content/v1/search/{quote(search_data.title)}', FetchCtx(capture=search_data.capture))
        videos = (search_results.get('data') or {}).get('videos') or [] if isinstance(search_results, dict) else []

        for v in videos:
            title = (v.get('title') or '').strip()
            slug = v.get('slug')
            if not title or not slug:
                continue

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=slug,
                    query=search_data.title,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([slug]),
                )
            )

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        base = site.base_url.rstrip('/')
        details_page_elements = await self.fetch_json(
            f'{base}/api/content/v1/videos/{payload}', FetchCtx(capture=ctx.capture if ctx else None, use_bypass=site.use_bypass)
        )
        item = (details_page_elements.get('data') or {}).get('item') if isinstance(details_page_elements, dict) else None
        if not isinstance(item, dict):
            return None

        return LoadedScene(
            url=f'{base}/api/content/v1/videos/{payload}', site=site, capture=ctx.capture if ctx else None, sel=None, html='', extra=item, source_json=item
        )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _item(self, scene: LoadedScene) -> dict[str, Any]:
        return scene.extra or {}

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.title = (self._item(scene).get('title') or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.summary = strip_tags(self._item(scene).get('description')) or ''

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = epoch_date(self._item(scene).get('publishedAt'))

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        genres = [(c.get('name') or '').strip() for c in (self._item(scene).get('categories') or [])]

        metadata.genres = [genre_name for genre_name in genres if genre_name]

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        base = scene.site.base_url.rstrip('/')
        actors: list[ActorResult] = []
        for m in self._item(scene).get('models') or []:
            actor_name = (m.get('title') or '').strip()
            if not actor_name:
                continue

            permalink = (m.get('featuredImage') or {}).get('permalink')
            if not permalink and m.get('slug'):
                model_page_elements = await self.fetch_json(f'{base}/api/content/v1/models/{m["slug"]}', FetchCtx(capture=scene.capture))
                permalink = (
                    (((model_page_elements.get('data') or {}).get('item') or {}).get('featuredImage') or {}).get('permalink')
                    if isinstance(model_page_elements, dict)
                    else None
                )

            photo = f'{base}{permalink}' if permalink else ''
            actors.append(ActorResult(name=actor_name, photo_url=photo, gender='female'))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        item = self._item(scene)
        base = scene.site.base_url.rstrip('/')
        images = self.image_collector(lambda image: image if image.startswith('http') else f'{base}{image}')
        for key in ('sliderImage', 'poster'):
            node = item.get(key) or {}
            images.push(node.get('permalink'))

        for img in item.get('galleryImages') or []:
            images.push(img.get('permalink'))

        metadata.art = images.items

        await self.enrich_from_data18(
            metadata,
            scene.site,
            scene_id=mapping_slug(metadata.title, scene.site.name),
            providers=_DATA18_PROVIDERS,
        )
