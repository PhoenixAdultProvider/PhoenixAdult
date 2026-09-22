from __future__ import annotations

import asyncio

from ddgs import DDGS
from ddgs.exceptions import DDGSException

from phoenixadult.utils.http.client import configured_https_proxy
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.searchengines.types import SearchOptions

_TIMEOUT = 10


class MetasearchClient:
    name = 'metasearch'

    def available(self) -> bool:
        return True

    def _run(self, query: str, num: int, safesearch: str) -> list[str]:
        rows = DDGS(proxy=configured_https_proxy(), timeout=_TIMEOUT).text(query, safesearch=safesearch, max_results=num)
        urls: list[str] = []
        for row in rows:
            href = str(row.get('href') or '')
            if href and href not in urls:
                urls.append(href)
        return urls

    async def search(self, opts: SearchOptions) -> list[str]:
        num = max(1, opts.num or 10)
        query = f'site:{opts.site} {opts.query}'
        safesearch = 'moderate' if opts.safe_search else 'off'
        logger.debug('search:meta', f'ddgs auto q="{query}"')
        try:
            urls = await asyncio.to_thread(self._run, query, num, safesearch)
        except DDGSException as err:
            logger.debug('search:meta', f'no results: {err}')
            return []
        sliced = urls[:num]
        logger.info('search:meta', f'site={opts.site} q="{opts.query}" → {len(sliced)} URL(s)')
        return sliced
