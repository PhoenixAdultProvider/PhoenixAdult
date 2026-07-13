from __future__ import annotations

import json

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import absolute_url, build_search_result, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text


class BrandNewAmateursClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        actor_url = f'{base}/models/{ctx.title.replace(" ", "")}.html'
        loaded = await self.fetch_and_load(actor_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] model "{ctx.title}"')
        if not loaded:
            return

        for card in loaded['sel'].xpath('//div[contains(@class,"item-video")]'):
            title = first_attr(card, '(.//div[contains(@class,"item-thumb")]//a/@title)[1]')
            href = first_attr(card, '(.//div[contains(@class,"item-thumb")]//a/@href)[1]')
            if not title or not href:
                continue
            scene_url = absolute_url(href, ctx.site_info.base_url)
            packed = json.dumps({'sceneURL': scene_url, 'actorURL': actor_url, 'releaseDate': ctx.search_date})
            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=ctx.title,
                    search_date=ctx.search_date,
                    cur_id=pack_cur_id([packed]),
                )
            )

    # ── Context loader (JSON-packed payload carries the actor page URL) ───────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        try:
            packed = json.loads(payload)
        except (ValueError, TypeError):
            packed = {'sceneURL': payload, 'actorURL': ''}
        scene_url = packed.get('sceneURL', '')
        loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture if ctx else None), f'[{site.name}] detail {scene_url}')
        if not loaded:
            return None
        return LoadedScene(
            url=scene_url,
            site=site,
            scene_date=packed.get('releaseDate') or None,
            capture=ctx.capture if ctx else None,
            sel=loaded['sel'],
            html=loaded['html'],
            extra=packed.get('actorURL', ''),
        )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = first_text(scene.sel, '//h3') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = first_text(scene.sel, '//div[contains(@class,"videoDetails") and contains(@class,"clear")]/p') or ''

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//ul[li[contains(.,"Tags:")]]//a')]
        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        actor_url = scene.extra if isinstance(scene.extra, str) else ''
        if not actor_url:
            return
        model = await self.fetch_and_load(actor_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] model page')
        if not model:
            return
        name = first_text(model['sel'], '//h3')
        if not name:
            return
        photo = first_attr(model['sel'], '(//div[contains(@class,"profile-pic")]//img/@src0_3x)[1]')
        if photo and not photo.startswith('http'):
            photo = absolute_url(photo, scene.site.base_url)
        metadata.actors = [ActorResult(name=name, photo_url=photo)]

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        poster = first_attr(scene.sel, '(//meta[contains(@name,"twitter:image")]/@content)[1]')
        if not poster:
            return
        metadata.raw_image_urls = [absolute_url(poster, scene.site.base_url)]
