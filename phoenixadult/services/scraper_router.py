from __future__ import annotations

import binascii

from phoenixadult.clients import get_client
from phoenixadult.models.scrape import SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.helpers import b64url_decode
from phoenixadult.utils.logging.context import scrape_phase_scope
from phoenixadult.utils.logging.logger import logger


class ScraperRouter:
    async def search(self, search_data: SearchContext | None) -> list[SearchResult] | None:
        if not search_data:
            return None
        client = get_client(search_data.site_info.scraper_config.type)
        if client is None:
            return None
        results: list[SearchResult] = []
        with scrape_phase_scope(f'search {search_data.site_info.name}'):
            await client.search(results, search_data)
        return results

    async def fetch_scene_detail(self, scene_url: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> SceneDetail | None:
        client = get_client(site.scraper_config.type)
        if client is None:
            return None
        with scrape_phase_scope(f'update {site.name}'):
            return await client.fetch_scene_detail(scene_url, site, ctx)

    def decode(self, cur_id: str) -> str:
        try:
            return b64url_decode(cur_id)
        except (UnicodeDecodeError, binascii.Error, ValueError):
            logger.debug('scraper', f'cur_id {cur_id} carries no scene URL')
            return ''
