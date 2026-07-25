from __future__ import annotations

import asyncio

from phoenixadult.clients.base import Client, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.config import config
from phoenixadult.registry.site_info import ResolvedSiteInfo
from phoenixadult.utils.cache import scene_store
from phoenixadult.utils.helpers.helpers import build_search_result, title_distance_score

MAX_RESULTS = 20


def _absolute(thumb: str) -> str | None:
    """Snapshot thumbs are stored host-relative; a search response needs a fetchable URL."""
    if not thumb:
        return None
    return f'{config.base_url}{thumb}' if thumb.startswith('/') else thumb


class ArchiveClient(Client):
    """Retired sites: nothing is left to scrape, so search reads the metadata cache and scene
    detail is a no-op — a stored scene stays matchable, it just never leaves the provider."""

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        rows = await asyncio.to_thread(scene_store.site_scenes, search_data.site_info.name)
        scored = [
            build_search_result(
                title=row['title'],
                scene_url='',
                query=search_data.title,
                search_date=search_data.search_date,
                display_date=row['release_date'] or None,
                score=title_distance_score(search_data.title, row['title']),
                cur_id=row['cur_id'],
                thumb_url=_absolute(row['thumb']),
            )
            for row in rows
        ]
        scored.sort(key=lambda result: result.score or 0, reverse=True)
        results.extend(scored[:MAX_RESULTS])

    async def fetch_scene_detail(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> SceneDetail | None:
        return None
