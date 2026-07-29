from __future__ import annotations

from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.searchengines.duckduckgo import DuckDuckGoClient
from phoenixadult.utils.searchengines.google_cse import GoogleCseClient
from phoenixadult.utils.searchengines.types import SearchEngineClient, SearchOptions

__all__ = ['SearchEngineClient', 'SearchOptions', 'web_search']


def _default_chain() -> list[SearchEngineClient]:
    return [GoogleCseClient(), DuckDuckGoClient()]


async def web_search(opts: SearchOptions) -> list[str]:
    for client in _default_chain():
        if not client.available():
            logger.debug('search', f'{client.name} unavailable — skipping')
            continue
        try:
            urls = await client.search(opts)
        except Exception as err:  # noqa: BLE001 - try the next client in the chain
            logger.warn('search', f'{client.name} threw: {err}; trying next in chain')
            continue
        if urls:
            logger.debug('search', f'{client.name} returned {len(urls)} URL(s); stopping chain')
            return urls
        logger.debug('search', f'{client.name} returned 0 URLs; trying next in chain')

    logger.warn('search', f'no client produced results for site={opts.site} q="{opts.query}"')
    return []
