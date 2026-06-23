from __future__ import annotations

from app.utils.logging.logger import logger
from app.utils.people.cache import cache_replace_enabled, lookup_cached
from app.utils.people.types import PersonLookupContext, PhotoHit


class _LocalStorageSource:
    name = 'Local Storage'

    async def find(self, actor_name: str, ctx: PersonLookupContext) -> PhotoHit | None:
        if cache_replace_enabled():
            logger.debug('localStorageSource', f'cache-replace forced; skipping cache for "{actor_name}"')
            return None
        hit = lookup_cached(actor_name, ctx.role)
        if not hit:
            logger.debug('localStorageSource', f'no cached photo for "{actor_name}" (role={ctx.role})')
            return None
        logger.debug('localStorageSource', f'hit "{actor_name}" → {hit["served_url"]} (gender={hit["gender"]})')
        return PhotoHit(url=hit['served_url'], gender=hit['gender'])  # type: ignore[arg-type]


local_storage_source = _LocalStorageSource()
