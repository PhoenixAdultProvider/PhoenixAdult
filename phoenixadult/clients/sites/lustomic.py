from __future__ import annotations

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import build_search_result, pack_cur_id
from phoenixadult.utils.helpers.html_helpers import first_attr


def _sibling_text(sel: Selector, alt: str, tag: str) -> str:
    return (sel.xpath(f'normalize-space((//img[@alt="{alt}"])[1]/following-sibling::{tag}[1])').get() or '').strip()


def _cast_names(sel: Selector) -> list[str]:
    raw = sel.xpath('normalize-space((//p[contains(.,"Starring")]//span)[1])').get() or ''
    return [n.strip() for n in raw.split(';') if n.strip()]


class LustomicClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        scene_url = search_data.search_url()

        search_results = await self.fetch_and_load(scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] sceneID {scene_url}')
        if not search_results:
            return

        title = _sibling_text(search_results['sel'], 'Video Preview', 'p')
        if not title:
            return

        results.append(
            build_search_result(
                site=search_data.site_info,
                title=title,
                scene_url=scene_url,
                query=search_data.title,
                search_date=search_data.search_date,
                cur_id=pack_cur_id([x for x in (scene_url, search_data.search_date) if x]),
            )
        )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = _sibling_text(details_page_elements, 'Video Preview', 'p') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = _sibling_text(details_page_elements, 'Video Description', 'div') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'Lustomic'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        cast = len(_cast_names(details_page_elements))
        if group := self.group_genre_for(cast):
            metadata.genres = [group]

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.actors = [ActorResult(name=actor_name, photo_url='', gender='') for actor_name in _cast_names(details_page_elements)]

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.art = self.dedup_strings([first_attr(a, '@href') for a in details_page_elements.xpath('//a[contains(@href,"video_preview_images")]')])
