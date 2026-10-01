from __future__ import annotations

from phoenixadult.config.env import env
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.people.cache import lookup_cached
from phoenixadult.utils.people.types import PersonLookupContext, PhotoHit


class _LocalStorageSource:
    name = 'Local Storage'

    async def find(self, actor_name: str, ctx: PersonLookupContext) -> PhotoHit | None:
        if env.people_cache_replace_enabled:
            logger.debug('localStorageSource', f'cache-replace forced; skipping cache for "{actor_name}"')
            return None
        hit = await run_in('store', lookup_cached, actor_name, ctx.type)
        if not hit:
            logger.debug('localStorageSource', f'no cached photo for "{actor_name}" (type={ctx.type})')
            return None
        logger.debug('localStorageSource', f'hit "{actor_name}" → {hit["served_url"]} (gender={hit["gender"]})')
        return PhotoHit(url=hit['served_url'], gender=hit['gender'])  # type: ignore[arg-type]


local_storage_source = _LocalStorageSource()
