from __future__ import annotations

from app.utils.logging.logger import logger
from app.utils.searchengines.duckduckgo import DuckDuckGoClient
from app.utils.searchengines.google_cse import GoogleCseClient
from app.utils.searchengines.types import SearchEngineClient, SearchOptions

__all__ = ['SearchEngineClient', 'SearchOptions', 'web_search', 'web_search_available', 'web_search_filtered']


def _default_chain() -> list[SearchEngineClient]:
    return [GoogleCseClient(), DuckDuckGoClient()]


def web_search_available() -> bool:
    """True if any engine in the chain can run (DuckDuckGo is zero-config so normally True);
    lets opt-in callers skip the web-search path entirely when no engine is usable."""
    return any(client.available() for client in _default_chain())


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


async def web_search_filtered(opts: SearchOptions, url_contains: str | None = None, url_ends_with: str | None = None) -> list[str]:
    found = await web_search(opts)
    out: list[str] = []
    for url in found:
        if url_contains and url_contains not in url:
            continue
        if url_ends_with and not url.endswith(url_ends_with):
            continue
        if url not in out:
            out.append(url)
    return out
