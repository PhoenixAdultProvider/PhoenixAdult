from __future__ import annotations

from phoenixadult.clients.base import Client, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry.site_info import ResolvedSiteInfo


class ArchiveClient(Client):
    """Retired sites: their scenes can only ever be served from the metadata cache, so this client
    never searches or scrapes — it exists to keep those scenes resolvable in the registry."""

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        return None

    async def fetch_scene_detail(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> SceneDetail | None:
        return None
