from __future__ import annotations

import re

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.helpers import build_search_result, pack_cur_id
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text

_COOKIE = {'Cookie': 'lang=en'}
_DIGITS_RE = re.compile(r'^\d+$')


class StasyQClient(Client):
    title_xpath = '//h1'
    summary_xpath = '//div[contains(@class,"about-section__text")]/p'
    genres_xpath = '//section[contains(@class,"about-section")]//div[contains(@class,"tags")]//a'

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        tokens = (search_data.full_title or search_data.title).split()
        scene_id = next((t for t in tokens if _DIGITS_RE.match(t)), None)
        if not scene_id:
            return

        scene_url = search_data.search_url(scene_id)
        search_results = await self.fetch_and_load(
            scene_url, FetchCtx(capture=search_data.capture, headers=_COOKIE), f'[{search_data.site_info.name}] sceneID {scene_id}'
        )
        if not search_results:
            return

        title = first_text(search_results['sel'], '//h1')
        if not title:
            return

        results.append(
            build_search_result(
                site=search_data.site_info,
                title=title,
                scene_url=scene_url,
                query=search_data.title,
                search_date=search_data.search_date,
                score=100,
                cur_id=pack_cur_id([scene_url]),
            )
        )

    # ── Context Loader ────────────────────────────────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        url, _, tail = payload.partition('|')
        scene_date = tail.strip() or None
        details_page_elements = await self.fetch_and_load(
            url, FetchCtx(capture=ctx.capture if ctx else None, headers=_COOKIE, use_bypass=site.use_bypass), f'[{site.name}] detail {url}'
        )
        if not details_page_elements:
            return None

        return LoadedScene(
            url=url,
            site=site,
            scene_date=scene_date,
            capture=ctx.capture if ctx else None,
            sel=details_page_elements['sel'],
            html=details_page_elements['html'],
        )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        actors: list[ActorResult] = []
        seen: set[str] = set()
        for actor_link in details_page_elements.xpath('//section[contains(@class,"content-section")]//div[contains(@class,"release-card__model")]//a'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            if actor_name and actor_name not in seen:
                seen.add(actor_name)
                actors.append(ActorResult(name=actor_name))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.art = self.dedup_strings(
            [(href or '').strip() for href in details_page_elements.xpath('//div[contains(@class,"js-release-gallery")]//a/@href').getall()]
        )
