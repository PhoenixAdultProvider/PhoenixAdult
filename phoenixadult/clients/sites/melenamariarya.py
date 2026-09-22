from __future__ import annotations

import re

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.html_helpers import first_text, meta_content
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result

_TITLE_SUFFIX = ' - Sex Movies Featuring Melena Maria Rya'


def _clean_title(raw: str, strip_four_k: bool) -> str:
    t = re.sub(r'[^A-Za-z0-9\s-]', ' ', raw.split(_TITLE_SUFFIX)[0]).strip()
    if strip_four_k:
        t = re.sub(r'\s+4\s*K(?:\s+Video)?$', '', t, flags=re.IGNORECASE).strip()

    return t


class MelenaMariaRyaClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        scene_id = search_data.title.strip().split()[0] if search_data.title.strip() else ''
        if not scene_id:
            return

        scene_url = f'{base}{search_data.site_info.search_path}{scene_id}'

        search_results = await self.fetch_and_load(scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] sceneID {scene_id}')
        if not search_results:
            return

        title = _clean_title(first_text(search_results['sel'], '//title'), False)
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
                cur_id=pack_cur_id([x for x in (scene_url, search_data.search_date) if x]),
            )
        )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = _clean_title(first_text(details_page_elements, '//title'), True) or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = meta_content(details_page_elements, 'description', 'name')

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.genres = ['European']

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        actors = [ActorResult(name='Melena Maria Rya', photo_url='', gender='')]
        co_star = re.search(r' with ([A-Za-z]+ [A-Za-z]+)$', _clean_title(first_text(details_page_elements, '//title'), True), re.IGNORECASE)
        if co_star:
            actors.append(ActorResult(name=co_star.group(1), photo_url='', gender=''))

        metadata.actors = actors
