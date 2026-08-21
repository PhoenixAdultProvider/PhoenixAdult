from __future__ import annotations

import json

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, pack_cur_id
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text


class BrandNewAmateursClient(Client):
    title_xpath = '//h3'
    summary_xpath = '//div[contains(@class,"videoDetails") and contains(@class,"clear")]/p'
    genres_xpath = '//ul[li[contains(.,"Tags:")]]//a'

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        actor_url = f'{base}/models/{search_data.title.replace(" ", "")}.html'
        model_page_elements = await self.fetch_and_load(
            actor_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] model "{search_data.title}"'
        )
        if not model_page_elements:
            return

        for card in model_page_elements['sel'].xpath('//div[contains(@class,"item-video")]'):
            title = first_attr(card, '(.//div[contains(@class,"item-thumb")]//a/@title)[1]')
            href = first_attr(card, '(.//div[contains(@class,"item-thumb")]//a/@href)[1]')
            if not title or not href:
                continue

            scene_url = absolute_url(href, search_data.site_info.base_url)
            packed = json.dumps({'sceneURL': scene_url, 'actorURL': actor_url, 'releaseDate': search_data.search_date})

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([packed]),
                )
            )

    # ── Context Loader (JSON-packed payload carries the actor page URL) ───────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        try:
            packed = json.loads(payload)
        except (ValueError, TypeError):
            packed = {'sceneURL': payload, 'actorURL': ''}

        scene_url = packed.get('sceneURL', '')
        details_page_elements = await self.fetch_and_load(
            scene_url, FetchCtx(capture=ctx.capture if ctx else None, use_bypass=site.use_bypass), f'[{site.name}] detail {scene_url}'
        )
        if not details_page_elements:
            return None

        return LoadedScene(
            url=scene_url,
            site=site,
            scene_date=packed.get('releaseDate') or None,
            capture=ctx.capture if ctx else None,
            sel=details_page_elements['sel'],
            html=details_page_elements['html'],
            extra=packed.get('actorURL', ''),
        )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        actor_url = scene.extra if isinstance(scene.extra, str) else ''
        if not actor_url:
            return

        model_page_elements = await self.fetch_and_load(actor_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] model page')
        if not model_page_elements:
            return

        actor_name = first_text(model_page_elements['sel'], '//h3')
        if not actor_name:
            return

        photo = first_attr(model_page_elements['sel'], '(//div[contains(@class,"profile-pic")]//img/@src0_3x)[1]')
        if photo and not photo.startswith('http'):
            photo = absolute_url(photo, scene.site.base_url)

        metadata.actors = [ActorResult(name=actor_name, photo_url=photo)]

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        poster = first_attr(details_page_elements, '(//meta[contains(@name,"twitter:image")]/@content)[1]')
        if not poster:
            return

        metadata.art = [absolute_url(poster, scene.site.base_url)]
